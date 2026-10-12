import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.mes.common import coderule
from app.mes.common.query import find, jsonable, one
from app.mes.common.rows import _ins

Row = dict[str, Any]
TERMINAL = ("completed", "scrapped", "merged")


def history(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    action: str,
    user: Any,
    step: Row | None = None,
    **kw: Any,
) -> None:
    step = (
        step if step is not None else one(s, tid, "route_step", lot["current_step_id"])
    )
    if step:
        kw.setdefault("route_step_id", step["id"])
        kw.setdefault("step_seq", step["seq"])
        kw.setdefault("operation_id", step["operation_id"])
    kw.setdefault("qty", lot["qty"])
    kw.setdefault("to_status", lot["lot_status"])
    if "details" in kw:
        kw["details"] = jsonable(kw["details"])
    _ins(
        s,
        tid,
        "lot_history",
        user,
        lot_id=lot["id"],
        action=action,
        user_email=getattr(user, "email", None),
        at=now(),
        **kw,
    )


def lock_lot(s: Session, tid: uuid.UUID, lot_id: uuid.UUID) -> Row:
    t = TABLES["lot"]
    r = (
        conn(s)
        .execute(
            sa.select(t).where(t.c.tenant_id == tid, t.c.id == lot_id).with_for_update()
        )
        .mappings()
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    return dict(r)


def tracking_level(s: Session, tid: uuid.UUID, product: Row | None) -> str:
    if product and product.get("tracking_level"):
        return str(product["tracking_level"])
    node = product and one(s, tid, "tech_node", product["tech_node_id"])
    return str((node and node["tracking_level"]) or "wafer")


def units(s: Session, tid: uuid.UUID, lot_id: Any, active: bool = True) -> list[Row]:
    rows = find(s, tid, "wafer", order="code", lot_id=lot_id)
    rows.sort(key=lambda u: (u["slot"] or 0, u["code"]))
    return [u for u in rows if not active or u["wafer_status"] not in ("scrapped",)]


# ---------------- lot start hook ----------------
def create_units(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    product: Row,
    slots: list[int],
    srcs: list[Any],
    wr: Row,
    user: Any,
    attrs: Row,
) -> str:
    """Units at lot start by tracking level; returns the level."""
    level = tracking_level(s, tid, product)
    at = now()
    if level == "quantity":
        return level
    if level == "unit":
        rule = one(s, tid, "code_rule", product["unit_code_rule_id"]) or wr
        codes = (
            coderule.generate(
                s, tid, rule, len(slots), {"LOT": lot["code"]}, commit=False
            )
            if "{SEQ" in rule["pattern"]
            else [
                coderule.render(rule, i, at, {"LOT": lot["code"], "SLOT": i})
                for i in range(1, len(slots) + 1)
            ]
        )
        for code, src in zip(codes, srcs, strict=True):
            _ins(
                s,
                tid,
                "wafer",
                user,
                code=code,
                lot_id=lot["id"],
                unit_kind=product["serial_kind"] or "unit",
                slot=None,
                wafer_status="waiting",
                source_ref=src or None,
                rework_count=0,
                attrs=dict(attrs),
            )
        return level
    seq_wafer = "{SEQ" in wr["pattern"]
    for k, src in zip(slots, srcs, strict=True):
        ctx = {"LOT": lot["code"], "SLOT": int(k)}
        wid = (
            coderule.generate(s, tid, wr, 1, ctx, commit=False)[0]
            if seq_wafer
            else coderule.render(wr, int(k), at, ctx)
        )
        _ins(
            s,
            tid,
            "wafer",
            user,
            code=wid,
            lot_id=lot["id"],
            unit_kind="wafer",
            slot=int(k),
            wafer_status="waiting",
            source_ref=src or None,
            rework_count=0,
            attrs=dict(attrs),
        )
    return level
