"""批次优先级变更（急件 / Hot Lot）：记录历史，执行 ``priority`` 时机的卡控。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.audit import audit
from app.core.spec.engine import ENTITIES
from app.core.spec.errors import coded, fe, http_422
from app.mes.common.query import one
from app.mes.common.rows import _upd
from app.mes.execution.checks import service as ck
from app.mes.execution.context import build_ctx
from app.mes.execution.stage_common import _brief, _ov, _result
from app.mes.lot.service import TERMINAL, history, lock_lot

Row = dict[str, Any]


def set_priority(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """变更批次优先级。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        body: ``{priority_id, comment, override, override_reason}``。
        user: 操作人。

    Returns:
        执行结果（批次、检查结果）。

    Raises:
        HTTPException: 参数不合法（422），卡控阻断（409）。
    """
    lot = lock_lot(s, tid, lot_id)
    if lot["lot_status"] in TERMINAL:
        raise http_422(
            [
                fe(
                    "lot_status",
                    ec.LOT_TERMINAL,
                    f"lot_status: lot is {lot['lot_status']}",
                    status=lot["lot_status"],
                )
            ]
        )
    pr = one(s, tid, "lot_priority", body.get("priority_id"))
    if not pr:
        raise http_422(
            [fe("priority_id", ec.PRIORITY_NOT_FOUND, "priority_id: not found")]
        )
    if pr["id"] == lot["priority_id"]:
        raise coded(409, ec.PRIORITY_UNCHANGED, "priority unchanged")
    old = one(s, tid, "lot_priority", lot["priority_id"])
    ctx = build_ctx(s, tid, lot, "priority", body)
    ctx.priority = pr
    results = ck.evaluate(
        ctx,
        user,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    _upd(s, tid, "lot", lot["id"], user, priority_id=pr["id"])
    history(
        s,
        tid,
        lot,
        "priority",
        user,
        comment=body.get("comment"),
        details={
            "from": old and old["code"],
            "to": pr["code"],
            "hot": bool(pr["is_hot"]),
            "checks": _brief(results),
            **_ov(body, results),
        },
    )
    audit(
        s,
        tid,
        ENTITIES["lot"],
        "priority",
        lot,
        user,
        {"priority": (old and old["code"], pr["code"])},
    )
    s.commit()
    return _result(s, tid, lot_id, results)
