"""批次 Hold：自动 Hold、释放、手工 Hold 与原因代码。"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import now
from app.core.spec.engine import ENTITIES
from app.core.spec.errors import http_422
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.lot.service import TERMINAL, history, lock_lot

Row = dict[str, Any]
LOT = ENTITIES["lot"]


# ---------------- holds ----------------
def default_reason(s: Session, tid: uuid.UUID, rtype: str) -> Row:
    """指定类型的默认原因代码（按编码排序的第一个启用项）。

    Raises:
        HTTPException: 未配置该类型的启用原因代码（422）。
    """
    rs = [
        r
        for r in find(s, tid, "reason_code", order="code", reason_type=rtype)
        if r["is_active"]
    ]
    if not rs:
        raise http_422(
            [("reason", f"reason: no active {rtype} reason code configured")]
        )
    return rs[0]


def _reason(
    s: Session, tid: uuid.UUID, rid: Any, rtype: str, field: str = "reason_id"
) -> Row:
    r = one(s, tid, "reason_code", rid)
    if not r or r["reason_type"] != rtype:
        raise http_422([(field, f"{field}: a {rtype} reason code is required")])
    return r


def hold_lot(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    user: Any,
    reason: Row,
    *,
    hold_type: str = "manual",
    source: str = "manual",
    comment: str | None = None,
    details: Row | None = None,
) -> uuid.UUID:
    """对批次加 Hold，并写历史。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot: 批次行。
        user: 操作人。
        reason: 原因代码行。
        hold_type: Hold 类型。
        source: 来源（manual / qtime / dc / check ...）。
        comment: 备注。
        details: 附加信息。

    Returns:
        新建 Hold 的 id。
    """
    hid = _ins(
        s,
        tid,
        "lot_hold",
        user,
        lot_id=lot["id"],
        reason_id=reason["id"],
        hold_type=hold_type,
        source=source,
        comment=(comment or "")[:300] or None,
        is_active=True,
        held_at=now(),
        held_by=getattr(user, "email", None) or "system",
        route_step_id=lot["current_step_id"],
    )
    _upd(s, tid, "lot", lot["id"], user, on_hold=True)
    lot["on_hold"] = True
    history(
        s,
        tid,
        lot,
        "hold",
        user,
        reason_id=reason["id"],
        comment=comment,
        details={"source": source, "hold_type": hold_type, **(details or {})},
    )
    audit(
        s,
        tid,
        LOT,
        "hold",
        lot,
        user,
        {"reason": (None, reason["code"]), "source": (None, source)},
    )
    return hid


def release_hold(
    s: Session,
    tid: uuid.UUID,
    hold_id: uuid.UUID,
    user: Any,
    reason_id: Any,
    comment: str | None,
) -> Row:
    """释放一条 Hold；批次无其他未释放 Hold 时恢复为非 Hold 状态。

    Raises:
        HTTPException: Hold 不存在（404）或已释放（422）。
    """
    h = one(s, tid, "lot_hold", hold_id)
    if not h:
        raise HTTPException(status_code=404, detail="Record not found")
    if not h["is_active"]:
        raise http_422([("hold", "hold: already released")])
    rr = (
        _reason(s, tid, reason_id, "release", "release_reason_id")
        if reason_id
        else None
    )
    _upd(
        s,
        tid,
        "lot_hold",
        hold_id,
        user,
        is_active=False,
        released_at=now(),
        released_by=getattr(user, "email", None),
        release_reason_id=rr and rr["id"],
        release_comment=(comment or "")[:300] or None,
    )
    lot = lock_lot(s, tid, h["lot_id"])
    left = [
        x
        for x in find(s, tid, "lot_hold", lot_id=lot["id"], is_active=True)
        if x["id"] != hold_id
    ]
    _upd(s, tid, "lot", lot["id"], user, on_hold=bool(left))
    lot["on_hold"] = bool(left)
    history(
        s,
        tid,
        lot,
        "release",
        user,
        reason_id=rr and rr["id"],
        comment=comment,
        details={"hold_id": str(hold_id), "remaining_holds": len(left)},
    )
    audit(s, tid, LOT, "resume", lot, user, {"release": (None, rr and rr["code"])})
    s.commit()
    return lot


def manual_hold(
    s: Session,
    tid: uuid.UUID,
    lot_id: uuid.UUID,
    reason_id: Any,
    comment: str | None,
    user: Any,
) -> Row:
    """手工 Hold（需原因代码），返回最新批次。"""
    lot = lock_lot(s, tid, lot_id)
    if lot["lot_status"] in TERMINAL:
        raise http_422([("lot_status", f"lot_status: lot is {lot['lot_status']}")])
    r = _reason(s, tid, reason_id, "hold")
    if r["comment_required"] and not (comment or "").strip():
        raise http_422([("comment", "comment: required for this reason code")])
    hold_lot(s, tid, lot, user, r, comment=comment)
    s.commit()
    return lot
