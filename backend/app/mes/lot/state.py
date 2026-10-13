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
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.core.spec.errors import http_422

Row = dict[str, Any]


class LotStatus(StrEnum):
    """批次流程状态（四段式过站，8 个状态，见 decisions.md #1）。"""

    WAITING = "waiting"
    MOVED_IN = "moved_in"
    RUNNING = "running"
    TRACKED_OUT = "tracked_out"
    COMPLETED = "completed"  # 待入库；仍算终态（decisions.md #6）
    STORED = "stored"
    SCRAPPED = "scrapped"
    MERGED = "merged"


S = LotStatus
ALL = frozenset(S)
TERMINAL = frozenset({S.COMPLETED, S.STORED, S.SCRAPPED, S.MERGED})
ACTIVE = ALL - TERMINAL


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
    "qtime_scrap": _r([S.WAITING], [S.SCRAPPED], hold=True),
    "change_carrier": _r(ACTIVE - {S.RUNNING}, hold=True),
    "priority": _r(ACTIVE, hold=True),
    # 终态批次不能被 Hold，含自动 Hold（decisions.md #4）
    "hold": _r(ACTIVE, hold=True),
    "release": _r(ALL, hold=True),
    "store": _r([S.COMPLETED], [S.STORED, S.COMPLETED]),
}


def check(lot: Row, action: str, to: str | None = None) -> LotStatus:
    """校验动作对批次是否合法，返回目标状态（不碰数据库）。

    Args:
        lot: 批次行（需含 lot_status、on_hold）。
        action: RULES 中的动作名。
        to: 多目标动作时调用方指定的目标状态。

    Returns:
        目标状态；状态不变的动作返回当前状态。

    Raises:
        HTTPException: 非法转移（422，字段 lot_status / on_hold）。
        KeyError: 未定义的动作（编程错误）。
    """
    rule = RULES[action]
    cur = str(lot["lot_status"])
    if cur not in rule.from_:
        msg = f"lot is {cur}" if cur in TERMINAL else f"cannot {action} a {cur} lot"
        raise http_422([("lot_status", f"lot_status: {msg}")])
    if lot.get("on_hold") and not rule.allow_hold:
        raise http_422([("on_hold", "on_hold: lot is on hold; release it first")])
    if not rule.targets:
        if to is not None and to != cur:
            raise http_422([("lot_status", f"lot_status: {action} cannot go to {to}")])
        return S(cur)
    if to is None:
        # 多目标且未指定时只校验起始状态与 Hold，目标由调用方随后再校验
        return next(iter(rule.targets)) if len(rule.targets) == 1 else S(cur)
    if to not in rule.targets:
        raise http_422(
            [("lot_status", f"lot_status: cannot {action} a {cur} lot to {to}")]
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
    except sa.exc.OperationalError as ex:
        if getattr(ex.orig, "sqlstate", None) != "55P03":  # lock_not_available
            raise
        raise HTTPException(
            status_code=409,
            detail={
                "code": "lot_busy",
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
        raise HTTPException(status_code=404, detail="Record not found")
    return out
