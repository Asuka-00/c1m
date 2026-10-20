"""预约 Hold（Future Hold）：在指定工步预设 Hold，批次到达该工步 Move In 时自动 Hold。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.base import now
from app.core.spec.engine import Entity
from app.core.spec.errors import MesError, fe
from app.core.spec.validate import validator
from app.mes.common.query import find, one
from app.mes.common.rows import _upd
from app.mes.execution.hold import default_reason, hold_lot
from app.mes.lot.service import TERMINAL

Row = dict[str, Any]


def pending(s: Session, tid: uuid.UUID, lot: Row, step_id: Any) -> list[Row]:
    """批次在某工步待触发的预约 Hold。"""
    return find(
        s,
        tid,
        "future_hold",
        order="created_at",
        lot_id=lot["id"],
        route_step_id=step_id,
        fh_status="active",
    )


def trigger(s: Session, tid: uuid.UUID, lot: Row, step: Row, user: Any) -> list[Row]:
    """触发当前工步的预约 Hold（调用方提交），返回已触发的预约。"""
    fired = []
    for fh in pending(s, tid, lot, step["id"]):
        reason = one(s, tid, "reason_code", fh["reason_id"]) or default_reason(
            s, tid, "hold"
        )
        hold_lot(
            s,
            tid,
            lot,
            user,
            reason,
            hold_type="future",
            source="future_hold",
            comment=fh["comment"],
            details={"future_hold_id": str(fh["id"]), "step_seq": step["seq"]},
        )
        _upd(
            s,
            tid,
            "future_hold",
            fh["id"],
            user,
            fh_status="triggered",
            triggered_at=now(),
        )
        fired.append(
            {"id": str(fh["id"]), "reason": reason["code"], "comment": fh["comment"]}
        )
    return fired


def _route_ids(s: Session, tid: uuid.UUID, route_id: Any, depth: int = 0) -> set[Any]:
    """路线及其调用的子流程（递归）。"""
    out = {route_id}
    if depth > 5:
        return out
    for st in find(s, tid, "route_step", route_id=route_id):
        if st["sub_route_id"]:
            out |= _route_ids(s, tid, st["sub_route_id"], depth + 1)
    return out


@validator("future_hold")
def _fh_save(s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None) -> None:
    """仅待触发的预约可修改；工步须在批次流程（含子流程）内，批次未结束。"""
    if old and old["fh_status"] != "active":
        raise MesError(
            [
                fe(
                    "fh_status",
                    ec.FH_NOT_EDITABLE,
                    "only waiting future holds can be edited",
                )
            ]
        )
    lot = one(s, tid, "lot", row.get("lot_id"))
    step = one(s, tid, "route_step", row.get("route_step_id"))
    if not lot or not step:
        return
    if lot["lot_status"] in TERMINAL:
        raise MesError(
            [
                fe(
                    "lot",
                    ec.LOT_TERMINAL,
                    f"lot: lot is {lot['lot_status']}",
                    status=lot["lot_status"],
                )
            ]
        )
    if step["route_id"] not in _route_ids(s, tid, lot["route_id"]):
        raise MesError(
            [
                fe(
                    "route_step",
                    ec.FH_STEP_NOT_ON_ROUTE,
                    "route_step: not on the lot's route",
                )
            ]
        )
