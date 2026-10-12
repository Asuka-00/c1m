import random
import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.mes.common.query import find, one

Row = dict[str, Any]


# ---------------- sampling / DC ----------------
def dc_plan_for(s: Session, tid: uuid.UUID, op_id: Any) -> Row | None:
    ps = [
        p
        for p in find(s, tid, "dc_plan", operation_id=op_id)
        if p["status"] == "active"
    ]
    return max(ps, key=lambda p: p["version"]) if ps else None


def sampling(s: Session, tid: uuid.UUID, lot: Row, step: Row, us: list[Row]) -> Row:
    op_id = step["operation_id"]
    if not op_id:
        return {
            "sampled": False,
            "items": [],
            "unit_ids": [],
            "message": "no operation",
        }
    rules = [
        r
        for r in find(s, tid, "sampling_rule", operation_id=op_id)
        if r["is_active"] and r["product_id"] in (None, lot["product_id"])
    ]
    rules.sort(key=lambda r: r["product_id"] is None)
    rule = rules[0] if rules else None
    plan = (
        one(s, tid, "dc_plan", rule["dc_plan_id"])
        if rule and rule["dc_plan_id"]
        else None
    ) or dc_plan_for(s, tid, op_id)
    if not plan:
        return {"sampled": False, "items": [], "unit_ids": [], "message": "no DC plan"}
    sampled, unit_ids, msg = True, [], "every lot (no sampling rule)"
    if rule:
        h = TABLES["lot_history"]
        n = (
            conn(s)
            .execute(
                sa.select(sa.func.count(sa.distinct(h.c.lot_id))).where(
                    h.c.tenant_id == tid,
                    h.c.operation_id == op_id,
                    h.c.action == "track_out",
                    h.c.lot_id != lot["id"],
                )
            )
            .scalar()
            or 0
        )
        freq = max(1, rule["lot_frequency"] or 1)
        sampled = n % freq == 0
        msg = f"rule {rule['code']}: lot {n + 1}, every {freq} → {'sampled' if sampled else 'skipped'}"
        if sampled and rule["level"] == "wafer" and us:
            k = min(len(us), rule["wafer_count"] or 1)
            sel = rule["wafer_selection"] or "first"
            if sel == "last":
                pick = us[-k:]
            elif sel == "alternate":
                pick = us[::2][:k]
            elif sel == "fixed":
                slots = {
                    int(x)
                    for x in (rule["fixed_slots"] or "").replace(" ", "").split(",")
                    if x.isdigit()
                }
                pick = [u for u in us if u["slot"] in slots]
            elif sel == "random":
                pick = sorted(
                    random.Random(lot["code"]).sample(us, k),
                    key=lambda u: u["slot"] or 0,
                )
            else:
                pick = us[:k]
            unit_ids = [str(u["id"]) for u in pick]
    items = []
    for it in find(s, tid, "dc_plan_item", order="seq", dc_plan_id=plan["id"]):
        mi = one(s, tid, "measurement_item", it["measurement_item_id"])
        if mi:
            items.append(
                {
                    "measurement_item_id": str(mi["id"]),
                    "code": mi["code"],
                    "name": mi["name"],
                    "meas_type": mi["meas_type"],
                    "lsl": it["lsl"],
                    "usl": it["usl"],
                    "target": it["target"],
                    "sites": it["sites"],
                    "oos_action": mi["oos_action"],
                }
            )
    return {
        "sampled": sampled,
        "rule": rule and rule["code"],
        "dc_plan_id": str(plan["id"]),
        "dc_plan": plan["code"],
        "unit_ids": unit_ids,
        "items": items,
        "message": msg,
    }


def _oos(it: Row, v: float) -> bool:
    return (it["lsl"] is not None and v < it["lsl"]) or (
        it["usl"] is not None and v > it["usl"]
    )
