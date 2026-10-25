"""批次 Hold：自动 Hold、释放、手工 Hold 与原因代码。"""

import logging
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.errors import coded, fe, http_422
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.execution.events import LOT_HOLD, notify_lot
from app.mes.lot.service import (
    HOLD_LIST_EXCLUDED,
    allowed,
    check_transition,
    history,
    lock_lot,
)

Row = dict[str, Any]
log = logging.getLogger(__name__)
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
        if r["is_active"] and not (r.get("attrs") or {}).get("system")
    ]  # 系统原因码（如 qtime_expired，D18）不作为默认原因
    if not rs:
        raise http_422(
            [
                fe(
                    "reason",
                    ec.REASON_MISSING,
                    f"reason: no active {rtype} reason code configured",
                    type=rtype,
                )
            ]
        )
    return rs[0]


def _reason(
    s: Session, tid: uuid.UUID, rid: Any, rtype: str, field: str = "reason_id"
) -> Row:
    r = one(s, tid, "reason_code", rid)
    if not r or r["reason_type"] != rtype:
        raise http_422(
            [
                fe(
                    field,
                    ec.REASON_REQUIRED,
                    f"{field}: a {rtype} reason code is required",
                    type=rtype,
                )
            ]
        )
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
    note: Row | None = None,
    details: Row | None = None,
    extra: Row | None = None,
) -> uuid.UUID | None:
    """对批次加 Hold，并写历史。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot: 批次行。
        user: 操作人。
        reason: 原因代码行。
        hold_type: Hold 类型。
        source: 来源（manual / qtime / dc / check ...）。
        comment: 人工备注。
        note: 系统生成的说明 ``{key, params}``（前端按 ``mes.sysNote.<key>`` 翻译）。
        details: 附加信息。
        extra: Hold 记录附加列（Q-Time 的 qtime_rule_id 等，D20）。

    Returns:
        新建 Hold 的 id；自动来源遇终态批次时跳过并返回 None。

    Raises:
        HTTPException: 手工 Hold 终态批次（422）。
    """
    if hold_type != "manual" and not allowed(lot, "auto_hold"):
        # 自动来源遇非在制批次（RULES["auto_hold"]，D17）：跳过，不写数据，记一行日志
        log.warning("skip %s hold on %s lot %s", source, lot["lot_status"], lot["code"])
        return None
    check_transition(lot, "hold")
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
        note=note,
        is_active=True,
        held_at=now(),
        held_by=actor_name(user) or "system",
        route_step_id=lot["current_step_id"],
        **(extra or {}),
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
    # 自动 Hold 通知（Q-Time 超时已由 qtime 事件通知；分批继承的 Hold 不重复通知）
    if hold_type in ("auto", "future") and source not in ("qtime", "split"):
        notify_lot(
            s,
            tid,
            LOT_HOLD,
            lot,
            f"Lot {lot['code']} auto hold ({source}): {reason['code']}",
            {"source": source, "reason": reason["code"], "comment": comment or ""},
            f"lot_hold:{hid}",
        )
    return hid


def _lock_hold(s: Session, tid: uuid.UUID, hold_id: uuid.UUID) -> Row:
    t = TABLES["lot_hold"]
    r = (
        conn(s)
        .execute(
            sa.select(t)
            .where(t.c.tenant_id == tid, t.c.id == hold_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not r:
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    return dict(r)


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
    lot = release(s, tid, hold_id, user, reason_id, comment)
    s.commit()
    return lot


def release(
    s: Session,
    tid: uuid.UUID,
    hold_id: Any,
    user: Any,
    reason_id: Any,
    comment: str | None,
) -> Row:
    """:func:`release_hold` 的不提交版本（供 NCR 处置等组合操作在同一事务内调用）。

    Raises:
        HTTPException: Hold 不存在（404）或已释放（422）。
    """
    h = one(s, tid, "lot_hold", hold_id)
    if not h:
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    # 锁顺序 lot → lot_hold；加锁后重读 Hold，防止并发重复释放
    lot = lock_lot(s, tid, h["lot_id"])
    h = _lock_hold(s, tid, hold_id)
    if not h["is_active"]:
        raise http_422([fe("hold", ec.HOLD_RELEASED, "hold: already released")])
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
        released_by=actor_name(user),
        release_reason_id=rr and rr["id"],
        release_comment=(comment or "")[:300] or None,
    )
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
    check_transition(lot, "hold")
    r = _reason(s, tid, reason_id, "hold")
    if r["comment_required"] and not (comment or "").strip():
        raise http_422(
            [
                fe(
                    "comment",
                    ec.COMMENT_REQUIRED,
                    "comment: required for this reason code",
                )
            ]
        )
    hold_lot(s, tid, lot, user, r, comment=comment)
    s.commit()
    return lot


QTIME_FIELDS = (
    "qtime_rule_id",
    "qtime_from_step_id",
    "qtime_to_step_id",
    "qtime_overdue_seconds",
)


def qtime_fields(h: Row) -> Row:
    """Hold 记录的 Q-Time 附加字段（D20）：id 转字符串，空值保持 None。"""
    return {
        k: (str(h.get(k)) if k.endswith("_id") and h.get(k) else h.get(k))
        for k in QTIME_FIELDS
    }


def _step_name(s: Session, tid: uuid.UUID, step_id: Any) -> str | None:
    """工步显示名：``<seq> <工序名>``（只读关联，不入库）。"""
    st = step_id and one(s, tid, "route_step", step_id)
    if not st:
        return None
    op = st["operation_id"] and one(s, tid, "operation", st["operation_id"])
    return f"{st['seq']} {op['name']}" if op else str(st["seq"])


def hold_row(s: Session, tid: uuid.UUID, h: Row, lot: Row, at: datetime) -> Row:
    """Hold 记录的接口形状（列表与详情一致）。"""
    rc = one(s, tid, "reason_code", h["reason_id"])
    rr = h["release_reason_id"] and one(s, tid, "reason_code", h["release_reason_id"])
    pr = one(s, tid, "product", lot["product_id"])
    st = one(s, tid, "route_step", h["route_step_id"])
    ha = h["held_at"]
    end = h["released_at"] if not h["is_active"] else at
    return {
        "id": str(h["id"]),
        "lot_id": str(lot["id"]),
        "lot": lot["code"],
        "lot_status": lot["lot_status"],
        "product": pr and pr["code"],
        "step_seq": st and st["seq"],
        "reason": rc and rc["code"],
        "reason_name": rc and rc["name"],
        "source": h["source"] or "manual",
        "hold_type": h["hold_type"],
        "is_active": bool(h["is_active"]),
        "held_at": ha and ha.isoformat(),
        "held_by": h["held_by"],
        "hours": ha and end and round((end - ha).total_seconds() / 3600, 1),
        "comment": h["comment"],
        "note": h.get("note"),
        "released_at": h["released_at"] and h["released_at"].isoformat(),
        "released_by": h["released_by"],
        "release_reason": rr and f"{rr['code']} · {rr['name'] or ''}",
        "release_comment": h["release_comment"],
        **qtime_fields(h),
        "qtime_from_step_name": _step_name(s, tid, h.get("qtime_from_step_id")),
        "qtime_to_step_name": _step_name(s, tid, h.get("qtime_to_step_id")),
    }


def get_hold(s: Session, tid: uuid.UUID, hold_id: Any) -> Row:
    """Hold 详情（形状同列表每条）。"""
    h = one(s, tid, "lot_hold", hold_id)
    lot = h and one(s, tid, "lot", h["lot_id"])
    if not h or not lot:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ec.HOLD_NOT_FOUND,
                "message": "Hold not found",
                "hold_id": str(hold_id),
            },
        )
    return hold_row(s, tid, h, lot, now())


def list_holds(
    s: Session,
    tid: uuid.UUID,
    active: bool | None = True,
    reason_id: Any = None,
    source: str | None = None,
    product_id: Any = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    *,
    include_terminal: bool = False,
) -> list[Row]:
    """Hold 列表（Hold 管理页）：默认仅生效中，可切换历史（已解除）或全部。

    Args:
        s: 数据库会话。
        tid: 租户 ID。
        active: ``True`` 生效中，``False`` 已解除（历史），``None`` 全部。
        reason_id: Hold 原因代码筛选。
        source: 来源筛选（manual / qtime / oos / split）。
        product_id: 产品筛选。
        date_from: Hold 时间下限（含）。
        date_to: Hold 时间上限（不含）。
        include_terminal: 是否包含终态批次的 Hold（默认排除，P15）。

    Returns:
        每条 ``{id, lot_id, lot, lot_status, product, step_seq, reason, reason_name, source,
        hold_type, is_active, held_at, held_by, hours, comment, released_at,
        released_by, release_reason, release_comment, qtime_rule_id,
        qtime_from_step_id, qtime_to_step_id, qtime_overdue_seconds,
        qtime_from_step_name, qtime_to_step_name}``，按 Hold 时间倒序。
    """
    at = now()
    if at.tzinfo:  # 无时区的查询参数按 UTC 处理
        date_from = date_from and (
            date_from if date_from.tzinfo else date_from.replace(tzinfo=at.tzinfo)
        )
        date_to = date_to and (
            date_to if date_to.tzinfo else date_to.replace(tzinfo=at.tzinfo)
        )
    out = []
    crit: dict[str, Any] = {} if active is None else {"is_active": active}
    for h in find(s, tid, "lot_hold", **crit):
        if reason_id and str(h["reason_id"]) != str(reason_id):
            continue
        if source and (h["source"] or "manual") != source:
            continue
        ha = h["held_at"]
        if date_from and (not ha or ha < date_from):
            continue
        if date_to and (not ha or ha >= date_to):
            continue
        lot = one(s, tid, "lot", h["lot_id"])
        if not lot or (product_id and str(lot["product_id"]) != str(product_id)):
            continue
        if not include_terminal and lot["lot_status"] in HOLD_LIST_EXCLUDED:
            continue
        out.append(hold_row(s, tid, h, lot, at))
    out.sort(key=lambda r: str(r["held_at"] or ""), reverse=True)
    return out


def release_batch(
    s: Session,
    tid: uuid.UUID,
    hold_ids: list[uuid.UUID],
    user: Any,
    reason_id: Any,
    comment: str | None,
) -> Row:
    """批量释放 Hold（须释放原因代码；原因要求备注时必须填写）。

    逐条释放，单条失败（已释放 / 不存在）不影响其他条目。

    Returns:
        ``{"released": [hold_id], "failed": [{"id", "error"}]}``。
    """
    r = _reason(s, tid, reason_id, "release", "reason_id")
    if r["comment_required"] and not (comment or "").strip():
        raise http_422(
            [
                fe(
                    "comment",
                    ec.COMMENT_REQUIRED,
                    "comment: required for this reason code",
                )
            ]
        )
    ok: list[str] = []
    bad: list[Row] = []
    for hid in dict.fromkeys(hold_ids):
        try:
            release_hold(s, tid, hid, user, r["id"], comment)
            ok.append(str(hid))
        except HTTPException as e:  # 校验失败发生在任何写入之前
            bad.append({"id": str(hid), "error": str(e.detail)})
    return {"released": ok, "failed": bad}
