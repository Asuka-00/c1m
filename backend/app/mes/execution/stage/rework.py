"""返工次数上限与跳站（Jump）。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.errors import FieldError, fe, http_422
from app.mes.common.query import one
from app.mes.common.rows import _upd
from app.mes.execution.checks import service as ck
from app.mes.execution.checks.types import M_RW
from app.mes.execution.stage.common import _brief, _ov, _result
from app.mes.execution.stage.context import build_ctx
from app.mes.lot.service import TERMINAL, history, lock_lot

Row = dict[str, Any]
LOT = ENTITIES["lot"]


def rework_count(s: Session, tid: uuid.UUID, lot_id: Any, step_id: Any) -> int:
    """批次在某工步进入返工路线的次数（批次级返工历史，不含单片返工标记）。"""
    h = TABLES["lot_history"]
    return int(
        conn(s)
        .execute(
            sa.select(sa.func.count()).where(
                h.c.tenant_id == tid,
                h.c.lot_id == lot_id,
                h.c.route_step_id == step_id,
                h.c.action == "rework",
                h.c.unit_id.is_(None),
            )
        )
        .scalar()
        or 0
    )


def rework_limit_result(ctx: ck.Ctx) -> Row | None:
    """进入返工前的「返工次数上限」检查结果（工步未设上限或开关关闭时为 None）。

    超限为可放行的阻断（block, overridable）。
    """
    mx = ctx.step.get("max_rework")
    if not mx or not ck.enabled(ctx, "rework_limit"):
        return None
    n = rework_count(ctx.s, ctx.tid, ctx.lot["id"], ctx.step["id"])
    if n >= mx:
        return ck.result(
            "rework_limit",
            "fail",
            M_RW("reached", step=ctx.step["seq"], count=n, max=mx),
            data={"count": n, "max": mx},
        )
    return ck.result(
        "rework_limit",
        "pass",
        M_RW("ok", next=n + 1, max=mx),
        data={"count": n, "max": mx},
    )


def jump(s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any) -> Row:
    """跳站：把等待中的批次移到同一流程的另一工步。

    仅限等待状态、非 Hold；需跳站原因代码（reason_type = jump）；执行触发时机 ``jump`` 的卡控。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        body: ``{to_step_id, reason_id, comment, override, override_reason}``。
        user: 操作人。

    Returns:
        执行结果（批次、检查结果）。

    Raises:
        HTTPException: 状态 / 目标工步 / 原因不合法（422），卡控阻断（409）。
    """
    lot = lock_lot(s, tid, lot_id)
    if lot["lot_status"] in TERMINAL or lot["lot_status"] != "waiting":
        raise http_422(
            [
                fe(
                    "lot_status",
                    ec.JUMP_STATUS,
                    f"lot_status: only waiting lots can jump ({lot['lot_status']})",
                    status=lot["lot_status"],
                )
            ]
        )
    if lot["on_hold"]:
        raise http_422(
            [fe("on_hold", ec.ON_HOLD, "on_hold: lot is on hold; release it first")]
        )
    cur = one(s, tid, "route_step", lot["current_step_id"])
    to = one(s, tid, "route_step", body.get("to_step_id"))
    errs: list[FieldError] = []
    if not cur or not to or to["route_id"] != cur["route_id"]:
        errs.append(
            fe(
                "to_step_id",
                ec.JUMP_STEP_ROUTE,
                "to_step_id: must be a step of the current route",
            )
        )
    elif to["id"] == cur["id"]:
        errs.append(
            fe("to_step_id", ec.JUMP_SAME_STEP, "to_step_id: already at this step")
        )
    elif not to.get("operation_id"):
        errs.append(
            fe(
                "to_step_id",
                ec.JUMP_STEP_OPERATION,
                "to_step_id: target must be an operation step",
            )
        )
    reason = one(s, tid, "reason_code", body.get("reason_id"))
    if not reason or reason["reason_type"] != "jump":
        errs.append(
            fe(
                "reason_id",
                ec.REASON_REQUIRED,
                "reason_id: a jump reason code is required",
                type="jump",
            )
        )
    elif reason.get("comment_required") and not (body.get("comment") or "").strip():
        errs.append(
            fe("comment", ec.COMMENT_REQUIRED, "comment: required by this reason code")
        )
    if errs:
        raise http_422(errs)
    assert cur and to and reason
    ctx = build_ctx(s, tid, lot, "jump", body)
    results = ck.evaluate(
        ctx,
        user,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    at = now()
    _upd(
        s,
        tid,
        "lot",
        lot["id"],
        user,
        current_step_id=to["id"],
        step_in_at=at,
        stage_at=at,
    )
    history(
        s,
        tid,
        lot,
        "jump",
        user,
        step=cur,
        reason_id=reason["id"],
        comment=(body.get("comment") or None),
        details={
            "from_seq": cur["seq"],
            "to_seq": to["seq"],
            "checks": _brief(results),
            **_ov(body, results),
        },
    )
    lot["current_step_id"] = to["id"]
    audit(
        s,
        tid,
        LOT,
        "jump",
        lot,
        user,
        {"current_step": (cur["seq"], to["seq"])},
    )
    s.commit()
    return _result(
        s, tid, lot_id, results, next_step={"id": str(to["id"]), "seq": to["seq"]}
    )
