"""E10 automatic state transitions triggered by execution events."""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn
from app.core.spec.engine import ENTITIES, TABLES
from app.mes.common.query import find, one
from app.mes.common.rows import _upd
from app.mes.equipment.status import e10_current

Row = dict[str, Any]


# ---------------- E10 ----------------
def e10_apply(
    s: Session, tid: uuid.UUID, eq: Row, trigger: str, user: Any, lot: Row
) -> Row | None:
    if trigger == "track_out":
        t = TABLES["lot"]
        others = (
            conn(s)
            .execute(
                sa.select(sa.func.count()).where(
                    t.c.tenant_id == tid,
                    t.c.equipment_id == eq["id"],
                    t.c.lot_status == "running",
                    t.c.id != lot["id"],
                )
            )
            .scalar()
        )
        if others:
            return {"skipped": f"{others} other lot(s) running"}
    rules = find(s, tid, "e10_auto_rule", trigger=trigger, is_active=True)
    rule = next(
        (r for r in rules if r["equipment_type_id"] == eq.get("equipment_type_id")),
        None,
    ) or next((r for r in rules if r["equipment_type_id"] is None), None)
    if not rule:
        return None
    cur = e10_current(s, tid, eq)
    to = one(s, tid, "e10_state", rule["to_state_id"])
    if not to or (cur and cur["id"] == to["id"]):
        return None
    if cur and not find(
        s, tid, "e10_transition", from_state_id=cur["id"], to_state_id=to["id"]
    ):
        return {"skipped": f"transition {cur['code']} -> {to['code']} not allowed"}
    _upd(s, tid, "equipment", eq["id"], user, e10_state_id=to["id"])
    audit(
        s,
        tid,
        ENTITIES["equipment"],
        "e10",
        eq,
        user,
        {"e10_state": (cur and cur["code"], to["code"])},
    )
    return {"equipment": eq["code"], "from": cur and cur["code"], "to": to["code"]}
