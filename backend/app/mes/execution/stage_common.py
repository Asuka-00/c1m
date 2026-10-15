"""阶段共享工具：前置校验、结果构造、放行处理、移动到下一工步。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import now
from app.core.spec.engine import ENTITIES
from app.core.spec.serialize import serialize
from app.mes.common.query import one
from app.mes.common.rows import _upd
from app.mes.lot.service import check_transition, history, units
from app.mes.process.service import next_location

Row = dict[str, Any]
LOT = ENTITIES["lot"]


# ---------------- stages ----------------
def _guard(lot: Row, stage: str) -> None:
    # 合法转移集中在 lot.state.RULES（running 中被 Hold 允许 track_out）
    check_transition(lot, stage)


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
        # 完工 = 待入库；工单完工数在入库单确认时累加（见 app.mes.warehouse）
        for u in units(s, tid, lot["id"]):
            _upd(s, tid, "wafer", u["id"], user, wafer_status="completed")
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
