"""Q-Time 超时处置：在 Move In 时或定时扫描时执行（警告 / Hold / 返工 / 报废）。

管控开关：Move In 触发时机上 ``qtime`` 类型规则严重度为 ``off`` 时（按工步 / 设备等作用域），
不执行超时处置。
"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.mes.common.query import find, one
from app.mes.common.rows import _upd
from app.mes.equipment.service import pm_notify
from app.mes.execution.checks import service as ck
from app.mes.execution.context import build_ctx
from app.mes.execution.events import QTIME_EXCEEDED, QTIME_WARN, notify_lot
from app.mes.execution.hold import default_reason, hold_lot
from app.mes.execution.stage_common import _relocate
from app.mes.lot.service import history, units

Row = dict[str, Any]


def _qtime_actions(
    s: Session, tid: uuid.UUID, lot: Row, step: Row, user: Any
) -> str | None:
    """执行最大 Q-Time 超时处置（每次超时只执行一次），返回处置结果。"""
    if not ck.enabled(build_ctx(s, tid, lot, "move_in", {}), "qtime"):
        return None
    h = TABLES["lot_history"]
    for x in ck.qtime_status(s, tid, lot, step, now()):
        if not x["exceeded"]:
            continue
        r = x["rule"]
        done = (
            conn(s)
            .execute(
                sa.select(h.c.details).where(
                    h.c.tenant_id == tid,
                    h.c.lot_id == lot["id"],
                    h.c.action == "qtime",
                    h.c.at >= x["since"],
                )
            )
            .scalars()
            .all()
        )
        if any((d or {}).get("rule_id") == str(r["id"]) for d in done):
            continue
        action = r["action"] or "hold"
        det = {
            "rule_id": str(r["id"]),
            "rule": r["code"],
            "minutes": x["minutes"],
            "max": r["max_minutes"],
            "action": action,
        }
        history(s, tid, lot, "qtime", user, reason_id=r["reason_id"], details=det)
        notify_lot(
            s,
            tid,
            QTIME_EXCEEDED,
            lot,
            f"Q-Time {r['code']} exceeded on {lot['code']}: "
            f"{x['minutes']:g} > {r['max_minutes']} min ({action})",
            {
                "rule": r["code"],
                "minutes": x["minutes"],
                "max": r["max_minutes"],
                "action": action,
            },
            f"qtime_exceeded:{lot['id']}:{r['id']}:{x['since'].isoformat()}",
        )
        if action == "warn":
            continue
        if action == "rework" and step["rework_route_id"]:
            _relocate(
                s,
                tid,
                lot,
                step,
                user,
                rework=True,
                branch=False,
                record_move_out=False,
            )
            return "rework"
        if action == "scrap":
            reason = one(s, tid, "reason_code", r["reason_id"]) or default_reason(
                s, tid, "scrap"
            )
            for u in units(s, tid, lot["id"]):
                _upd(
                    s,
                    tid,
                    "wafer",
                    u["id"],
                    user,
                    wafer_status="scrapped",
                    scrap_reason_id=reason["id"],
                )
            _upd(
                s,
                tid,
                "lot",
                lot["id"],
                user,
                lot_status="scrapped",
                scrapped_qty=(lot["scrapped_qty"] or 0) + lot["qty"],
                qty=0,
            )
            lot.update(lot_status="scrapped", qty=0)
            history(
                s,
                tid,
                lot,
                "scrap",
                user,
                reason_id=reason["id"],
                details={"source": "qtime", "rule": r["code"]},
            )
            return "scrap"
        reason = one(s, tid, "reason_code", r["reason_id"]) or default_reason(
            s, tid, "hold"
        )
        hold_lot(
            s,
            tid,
            lot,
            user,
            reason,
            hold_type="auto",
            source="qtime",
            comment=f"Q-Time {r['code']}: {x['minutes']:g} > {r['max_minutes']} min",
            details=det,
        )
        return "hold"
    return None


def qtime_monitor(s: Session, tid: uuid.UUID) -> list[Row]:
    """Q-Time 监控：等待中批次在当前工步（终点）上的各条 Q-Time 规则计时。

    Returns:
        每批次每规则一行：批次、工步、规则、已用 / 上限分钟、剩余分钟、是否超时、是否预警（达到预警阈值）、处置动作。
    """
    at = now()
    out: list[Row] = []
    for lot in find(s, tid, "lot", lot_status="waiting"):
        step = one(s, tid, "route_step", lot["current_step_id"])
        if not step:
            continue
        for x in ck.qtime_status(s, tid, lot, step, at):
            r = x["rule"]
            mx = r["max_minutes"]
            out.append(
                {
                    "lot_id": str(lot["id"]),
                    "lot": lot["code"],
                    "on_hold": bool(lot["on_hold"]),
                    "step_seq": step["seq"],
                    "rule": r["code"],
                    "since": x["since"].isoformat(),
                    "minutes": x["minutes"],
                    "max_minutes": mx,
                    "remaining": round(mx - x["minutes"], 1) if mx else None,
                    "exceeded": x["exceeded"],
                    "warn": x["warn"],
                    "warn_minutes": r.get("warn_minutes"),
                    "action": r["action"] or "hold",
                }
            )
    out.sort(key=lambda r: (r["remaining"] is None, r["remaining"] or 0))
    return out


def _qtime_warn(s: Session, tid: uuid.UUID, lot: Row, step: Row) -> int:
    """Q-Time 预警通知：达到预警阈值且未超时的规则各通知一次（按计时起点去重）。"""
    sts = [x for x in ck.qtime_status(s, tid, lot, step, now()) if x["warn"]]
    if not sts or not ck.enabled(build_ctx(s, tid, lot, "move_in", {}), "qtime"):
        return 0
    n = 0
    for x in sts:
        r = x["rule"]
        left = (r["max_minutes"] or 0) - x["minutes"]
        n += bool(
            notify_lot(
                s,
                tid,
                QTIME_WARN,
                lot,
                f"Q-Time {r['code']} on {lot['code']} expires in {left:g} min",
                {
                    "rule": r["code"],
                    "minutes": x["minutes"],
                    "max": r["max_minutes"],
                    "left": round(left, 1),
                },
                f"qtime_warn:{lot['id']}:{r['id']}:{x['since'].isoformat()}",
            )
        )
    return n


def sweep_qtime(s: Session, tid: uuid.UUID, user: Any) -> Row:
    """Q-Time 超时扫描：对等待中、未 Hold 的超时批次立即执行处置（幂等）。

    可由前端手动触发或外部调度器定时调用；每条超时只处置一次，管控开关关闭的工步跳过。

    Returns:
        ``{"checked": 扫描批次数, "actions": [{"lot", "action"}]}``。
    """
    acted: list[Row] = []
    lots = [x for x in find(s, tid, "lot", lot_status="waiting") if not x["on_hold"]]
    for lot in lots:
        step = one(s, tid, "route_step", lot["current_step_id"])
        if not step:
            continue
        _qtime_warn(s, tid, lot, step)
        a = _qtime_actions(s, tid, lot, step, user)
        if a:
            acted.append({"lot": lot["code"], "action": a})
    s.commit()
    return {"checked": len(lots), "actions": acted}


def sweep_all_tenants(only: list[uuid.UUID] | None = None) -> Row:
    """全部租户的定时扫描（后台任务调用）：Q-Time 预警 / 超时处置、PM 到期通知。

    通过 Postgres 事务级咨询锁保证多进程 / 多实例下同一时刻只有一个执行者；
    每个租户独立会话（设置 RLS 租户上下文），单租户失败不影响其他租户。

    Args:
        only: 仅扫描这些租户（测试 / 手工补跑用），None 为全部。

    Returns:
        ``{"tenants": 扫描租户数, "actions": 处置条数}``，未取得锁时 ``{"skipped": True}``。
    """
    import logging

    from sqlmodel import select

    from app.core.db import engine
    from app.core.tenant import set_tenant
    from app.platform.tenants.models import Tenant

    log = logging.getLogger(__name__)
    with Session(engine) as lock_s:
        got = (
            lock_s.connection()
            .execute(sa.text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": QTIME_LOCK})
            .scalar()
        )
        if not got:
            return {"skipped": True}
        tids = list(lock_s.exec(select(Tenant.id)).all())
        if only is not None:
            tids = [t for t in tids if t in set(only)]
        n = 0
        for tid in tids:
            with Session(engine) as s:
                set_tenant(s, tid)
                try:
                    n += len(sweep_qtime(s, tid, None)["actions"])
                    n += pm_notify(s, tid)
                    s.commit()
                except Exception:  # noqa: BLE001 - 单租户失败只记录日志
                    log.exception("qtime sweep failed for tenant %s", tid)
        return {"tenants": len(tids), "actions": n}


#: Q-Time 扫描咨询锁键
QTIME_LOCK = 72_160_401
