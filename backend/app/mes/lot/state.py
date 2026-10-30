"""批次状态机：合法转移的唯一定义处（见 architect/design/lot-state-machine.md §4）。

流程状态 ``lot_status`` 与 Hold 标志 ``on_hold`` 是两个正交维度。所有
"某动作能否作用于某状态的批次"的判断都应经 :func:`check`，不在表里的组合一律拒绝。
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
import sqlalchemy.exc
from fastapi import HTTPException
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.core.spec.errors import coded

Row = dict[str, Any]


class LotStatus(StrEnum):
    """批次流程状态（四段式过站 8 个状态，见 decisions.md #1；另加 Bank 在库 / 领出）。"""

    WAITING = "waiting"
    MOVED_IN = "moved_in"
    RUNNING = "running"
    TRACKED_OUT = "tracked_out"
    COMPLETED = "completed"  # 待入库；仍算终态（decisions.md #6）
    STORED = "stored"
    SCRAPPED = "scrapped"
    MERGED = "merged"
    BANKED = "banked"  # 前道完工后在 Bank 中等待封测领用；不算在制
    ISSUED = "issued"  # 已从 Bank 全部领出到新批次（终止）


S = LotStatus
ALL = frozenset(S)
TERMINAL = frozenset({S.COMPLETED, S.STORED, S.SCRAPPED, S.MERGED, S.BANKED, S.ISSUED})
ACTIVE = ALL - TERMINAL

# 可被 Hold 的状态（手动 + 自动，D4 经 M2 修订：completed/stored 允许；在库批次同理）
HOLDABLE: frozenset[LotStatus] = ACTIVE | {S.COMPLETED, S.STORED, S.BANKED}
# 可被自动 Hold 的状态（D17）
AUTO_HOLDABLE: frozenset[LotStatus] = ACTIVE
# Hold 列表默认排除的批次状态（N6 经 M2 修订）；include_terminal=true 时显示全部
HOLD_LIST_EXCLUDED: frozenset[LotStatus] = frozenset({S.SCRAPPED, S.MERGED, S.ISSUED})


@dataclass(frozen=True)
class Rule:
    """一个动作的合法转移规则。

    Attributes:
        from_: 允许的起始状态。
        targets: 允许的目标状态；为空表示状态不变。
        allow_hold: on_hold=True 时是否允许。
    """

    from_: frozenset[LotStatus]
    targets: frozenset[LotStatus] = frozenset()
    allow_hold: bool = False


def _r(frm: Iterable[S], to: Iterable[S] = (), hold: bool = False) -> Rule:
    return Rule(frozenset(frm), frozenset(to), hold)


RULES: dict[str, Rule] = {
    "undo_start": _r([S.WAITING]),
    "move_in": _r([S.WAITING], [S.MOVED_IN]),
    "track_in": _r([S.MOVED_IN], [S.RUNNING]),
    # 加工中被 Hold 允许完成 Track Out，但不能 Move Out（decisions.md #2）
    "track_out": _r([S.RUNNING], [S.TRACKED_OUT, S.SCRAPPED], hold=True),
    "move_out": _r([S.TRACKED_OUT], [S.WAITING, S.COMPLETED]),
    "jump": _r([S.WAITING]),
    "split": _r([S.WAITING, S.MOVED_IN], hold=True),
    "merge_source": _r([S.WAITING, S.MOVED_IN], [S.MERGED]),
    "merge_target": _r([S.WAITING, S.MOVED_IN]),
    # 加工中不能报废（decisions.md #3）
    "scrap": _r(ACTIVE - {S.RUNNING}, [S.SCRAPPED], hold=True),
    "adjust": _r(ACTIVE, hold=True),
    "change_carrier": _r(ACTIVE - {S.RUNNING}, hold=True),
    "priority": _r(ACTIVE, hold=True),
    "hold": _r(HOLDABLE, hold=True),  # 手动 Hold（D13）
    # 自动 Hold（qtime / oos / future 等，D17）：只作用于在制批次，其余由调用方跳过
    "auto_hold": _r(AUTO_HOLDABLE, hold=True),
    "release": _r(ALL, hold=True),
    "store": _r([S.COMPLETED], [S.STORED, S.COMPLETED]),
    "bank_in": _r([S.COMPLETED], [S.BANKED]),
    # 部分领用仍留在 Bank，全部领出则终止
    "bank_out": _r([S.BANKED], [S.BANKED, S.ISSUED]),
    # 单元转换（晶圆 → 芯片 / 条带 / 单颗）只在工步前后进行，不能在加工中
    "convert": _r([S.WAITING, S.MOVED_IN]),
    # 出货（D13 / H2-02）：仅 stored 且不能持 Hold；状态不变（D1 维持 8 个状态，
    # 无 shipped），只累加 shipped_qty，见 warehouse/shipment.py
    "ship": _r([S.STORED]),
}


def lot_error(
    code: int, message: str, lot: Row | None = None, **extra: Any
) -> HTTPException:
    """批次业务错误（N5）：``detail = {code, message, lot_id?, lot_code?, ...}``，422。"""
    d: Row = {"code": code, "message": message}
    if lot is not None:
        d.update(
            lot_id=str(lot.get("id")) if lot.get("id") else None,
            lot_code=lot.get("code"),
        )
    d.update(extra)
    return HTTPException(status_code=422, detail=d)


def check(lot: Row, action: str, to: str | None = None) -> LotStatus:
    """校验动作对批次是否合法，返回目标状态（不碰数据库）。

    Args:
        lot: 批次行（需含 lot_status、on_hold）。
        action: RULES 中的动作名。
        to: 多目标动作时调用方指定的目标状态。

    Returns:
        目标状态；状态不变的动作返回当前状态。

    Raises:
        HTTPException: 非法转移（422，detail.code = lot_status / on_hold）。
        KeyError: 未定义的动作（编程错误）。
    """
    rule = RULES[action]
    cur = str(lot["lot_status"])
    ctx = {"action": action, "lot_status": cur}
    if cur not in rule.from_:
        msg = f"lot is {cur}" if cur in TERMINAL else f"cannot {action} a {cur} lot"
        raise lot_error(ec.LOT_STATUS, msg, lot, **ctx)
    if lot.get("on_hold") and not rule.allow_hold:
        raise lot_error(ec.ON_HOLD, "lot is on hold; release it first", lot, **ctx)
    if not rule.targets:
        if to is not None and to != cur:
            raise lot_error(ec.LOT_STATUS, f"{action} cannot go to {to}", lot, **ctx)
        return S(cur)
    if to is None:
        # 多目标且未指定时只校验起始状态与 Hold，目标由调用方随后再校验
        return next(iter(rule.targets)) if len(rule.targets) == 1 else S(cur)
    if to not in rule.targets:
        raise lot_error(
            ec.LOT_STATUS, f"cannot {action} a {cur} lot to {to}", lot, **ctx
        )
    return S(to)


check_transition = check


def allowed(lot: Row, action: str) -> bool:
    """:func:`check` 的布尔版本（用于 UI 提示 / 预检）。"""
    try:
        check(lot, action)
    except HTTPException:
        return False
    return True


LOCK_TIMEOUT = "5s"


def locked(s: Session, stmt: Any) -> list[Row]:
    """执行 FOR UPDATE 查询；锁等待超过 LOCK_TIMEOUT 时返回 409 lot_busy（P16）。

    Raises:
        HTTPException: 锁等待超时（409，detail.code=lot_busy）。
    """
    c = conn(s)
    c.execute(sa.text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    try:
        rows = c.execute(stmt).mappings().all()
    except sqlalchemy.exc.OperationalError as ex:
        if getattr(ex.orig, "sqlstate", None) != "55P03":  # lock_not_available
            raise
        raise HTTPException(
            status_code=409,
            detail={
                "code": ec.LOT_BUSY,
                "message": "lot is locked by another operation",
            },
        ) from ex
    return [dict(r) for r in rows]


def lock_order(ids: Iterable[Any]) -> list[uuid.UUID]:
    """多批次加锁的固定顺序：去重后按 id 升序（防死锁）。"""
    return sorted({uuid.UUID(str(x)) for x in ids})


def lock_lots(s: Session, tid: uuid.UUID, ids: Iterable[Any]) -> dict[uuid.UUID, Row]:
    """按 id 升序一次性 SELECT ... FOR UPDATE 锁定多个批次。

    Raises:
        HTTPException: 任一批次不存在（404）。
    """
    order = lock_order(ids)
    if not order:
        return {}
    t = TABLES["lot"]
    rows = locked(
        s,
        sa.select(t)
        .where(t.c.tenant_id == tid, t.c.id.in_(order))
        .order_by(t.c.id)
        .with_for_update(),
    )
    out = {r["id"]: dict(r) for r in rows}
    if len(out) != len(order):
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    return out
