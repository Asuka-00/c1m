"""Shared stage helpers: guards, results, overrides, relocation to the next step."""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import now
from app.core.spec.engine import ENTITIES
from app.core.spec.errors import http_422
from app.core.spec.serialize import serialize
from app.mes.common.query import one
from app.mes.common.rows import _upd
from app.mes.execution.constants import FROM_STATUS
from app.mes.lot.service import TERMINAL, history, units
from app.mes.process.service import next_location

Row = dict[str, Any]
LOT = ENTITIES["lot"]


# ---------------- stages ----------------
def _guard(lot: Row, stage: str) -> None:
    if lot["lot_status"] in TERMINAL:
        raise http_422([("lot_status", f"lot_status: lot is {lot['lot_status']}")])
    if lot["on_hold"]:
        raise http_422([("on_hold", "on_hold: lot is on hold; release it first")])
    if lot["lot_status"] != FROM_STATUS[stage]:
        raise http_422(
            [("lot_status", f"lot_status: cannot {stage} a {lot['lot_status']} lot")]
        )


def _result(
    s: Session, tid: uuid.UUID, lot_id: Any, results: list[Row], **extra: Any
) -> Row:
    lot = one(s, tid, "lot", lot_id)
    return {
        "lot": serialize(s, tid, LOT, [lot])[0] if lot else None,
        "results": results,
        **extra,
    }


def _relocate(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    step: Row,
    user: Any,
    *,
    branch: bool,
    rework: bool,
    record_move_out: bool = True,
) -> Row | None:
    nxt, stack, ev = next_location(s, tid, lot, step, branch=branch, rework=rework)
    at = now()
    if record_move_out:
        history(
            s,
            tid,
            lot,
            "move_out",
            user,
            step=step,
            from_status="tracked_out",
            to_status="waiting" if nxt else "completed",
            equipment_id=lot["equipment_id"],
        )
    for e in ev:
        st = e.pop("step")
        history(s, tid, lot, e.pop("action"), user, step=st, details=e)
    vals: Row = {
        "equipment_id": None,
        "recipe_id": None,
        "exec_ctx": None,
        "pending_rework": False,
        "stage_at": at,
        "route_stack": stack,
    }
    if nxt is None:
        vals.update(lot_status="completed", completed_at=at)
        for u in units(s, tid, lot["id"]):
            _upd(s, tid, "wafer", u["id"], user, wafer_status="completed")
        wo = one(s, tid, "work_order", lot["work_order_id"])
        if wo:
            _upd(
                s,
                tid,
                "work_order",
                wo["id"],
                user,
                completed_qty=(wo["completed_qty"] or 0) + lot["qty"],
            )
    else:
        vals.update(lot_status="waiting", current_step_id=nxt["id"], step_in_at=at)
        for u in units(s, tid, lot["id"]):
            if u["wafer_status"] == "rework" and rework:
                continue
            if u["wafer_status"] in ("rework",):
                _upd(s, tid, "wafer", u["id"], user, wafer_status="waiting")
    _upd(s, tid, "lot", lot["id"], user, **vals)
    lot.update(vals)
    if nxt is None:
        history(
            s,
            tid,
            lot,
            "complete",
            user,
            step=step,
            details={"completed_qty": lot["qty"]},
        )
        audit(
            s,
            tid,
            LOT,
            "complete",
            lot,
            user,
            {"lot_status": ("tracked_out", "completed")},
        )
    return nxt


def _brief(results: list[Row]) -> list[Row]:
    return [
        {
            "type": r["check_type"],
            "rule": r["rule_code"],
            "result": r["result"],
            "message": r["message"],
        }
        for r in results
        if r["applicable"] or r["result"] != "pass"
    ]


def _ov(body: Row, results: list[Row]) -> Row:
    if any(r["result"] == "overridden" for r in results):
        return {"override_reason": body.get("override_reason")}
    return {}
