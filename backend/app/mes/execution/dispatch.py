"""现场作业视图：派工队列（批次作业页）与首页概览。"""

import uuid
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.mes.common.query import find, one
from app.mes.equipment.service import e10_current, pm_status
from app.mes.execution.checks import service as ck
from app.mes.lot.service import TERMINAL

Row = dict[str, Any]


def _last_moves(s: Session, tid: uuid.UUID) -> dict[Any, datetime]:
    h = TABLES["lot_history"]
    q = (
        sa.select(h.c.lot_id, sa.func.max(h.c.at).label("at"))
        .where(h.c.tenant_id == tid)
        .group_by(h.c.lot_id)
    )
    return {r.lot_id: r.at for r in conn(s).execute(q)}


def queue(
    s: Session,
    tid: uuid.UUID,
    *,
    q: str | None = None,
    lot_status: str | None = None,
    operation_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    on_hold: bool | None = None,
) -> list[Row]:
    """派工队列：在制（非终态）批次，按“非 Hold → 优先级 → Q-Time 剩余 → 滞留时长”排序。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        q: 批次号模糊匹配。
        lot_status: 批次状态。
        operation_id: 当前工步的工序。
        product_id: 产品。
        on_hold: 是否 Hold。

    Returns:
        行：批次、产品、工步 / 工序、状态、优先级、Hold、Q-Time 最小剩余分钟、滞留小时。
    """
    t = TABLES["lot"]
    stmt = sa.select(t).where(t.c.tenant_id == tid, t.c.lot_status.not_in(TERMINAL))
    if q:
        stmt = stmt.where(t.c.code.ilike(f"%{q}%"))
    if lot_status:
        stmt = stmt.where(t.c.lot_status == lot_status)
    if product_id:
        stmt = stmt.where(t.c.product_id == product_id)
    if on_hold is not None:
        stmt = stmt.where(t.c.on_hold.is_(on_hold))
    lots = [dict(r) for r in conn(s).execute(stmt).mappings()]
    last = _last_moves(s, tid)
    at = now()
    cache: dict[tuple[str, Any], Row | None] = {}

    def get(e: str, rid: Any) -> Row | None:
        if (e, rid) not in cache:
            cache[(e, rid)] = one(s, tid, e, rid) if rid else None
        return cache[(e, rid)]

    out: list[Row] = []
    for lot in lots:
        step = get("route_step", lot["current_step_id"])
        op = step and get("operation", step["operation_id"])
        if operation_id and (not op or op["id"] != operation_id):
            continue
        pr = get("lot_priority", lot.get("priority_id"))
        prod = get("product", lot["product_id"])
        rem = None
        if step and lot["lot_status"] == "waiting":
            rs = [
                x["rule"]["max_minutes"] - x["minutes"]
                for x in ck.qtime_status(s, tid, lot, step, at)
                if x["rule"]["max_minutes"]
            ]
            rem = round(min(rs), 1) if rs else None
        since = last.get(lot["id"]) or lot.get("created_at")
        out.append(
            {
                "id": str(lot["id"]),
                "code": lot["code"],
                "product": prod and prod["code"],
                "step_seq": step and step["seq"],
                "operation": op and op["code"],
                "operation_name": op and op["name"],
                "lot_status": lot["lot_status"],
                "qty": lot["qty"],
                "priority": pr and pr["code"],
                "priority_level": pr and pr["level"],
                "priority_color": pr and pr.get("color"),
                "on_hold": bool(lot["on_hold"]),
                "qtime_remaining": rem,
                "hours": since and round((at - since).total_seconds() / 3600, 1),
            }
        )
    out.sort(
        key=lambda r: (
            r["on_hold"],
            r["priority_level"] if r["priority_level"] is not None else 999,
            r["qtime_remaining"] if r["qtime_remaining"] is not None else 1e9,
            -(r["hours"] or 0),
        )
    )
    return out


def home(s: Session, tid: uuid.UUID) -> Row:
    """首页概览：在制、Hold、Q-Time 预警 / 超时、设备状态分布、PM 到期、今日出站。"""
    t = TABLES["lot"]
    c = conn(s)
    active = sa.and_(t.c.tenant_id == tid, t.c.lot_status.not_in(TERMINAL))
    lots, qty, held = c.execute(
        sa.select(
            sa.func.count(),
            sa.func.coalesce(sa.func.sum(t.c.qty), 0),
            sa.func.count().filter(t.c.on_hold.is_(True)),
        ).where(active)
    ).one()
    at = now()
    warn = exceeded = 0
    for lot in find(s, tid, "lot", lot_status="waiting"):
        step = one(s, tid, "route_step", lot["current_step_id"])
        for x in ck.qtime_status(s, tid, lot, step, at) if step else []:
            exceeded += int(bool(x["exceeded"]))
            warn += int(bool(x["warn"]))
    states: dict[str, Row] = {}
    pm_due = pm_warn = 0
    for eq in find(s, tid, "equipment", unit_kind="main", is_active=True):
        cur = e10_current(s, tid, eq)
        key = cur["e10_category"] if cur else "—"
        st = states.setdefault(
            key, {"category": key, "color": cur and cur.get("color"), "count": 0}
        )
        st["count"] += 1
        for p in pm_status(s, tid, eq):
            pm_due += int(bool(p["due"]))
            pm_warn += int(bool(p["warn"]) and not p["due"])
    h = TABLES["lot_history"]
    tz = datetime.now().astimezone().tzinfo
    day0 = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    moves = c.execute(
        sa.select(sa.func.count()).where(
            h.c.tenant_id == tid,
            h.c.action == "track_out",
            h.c.at >= day0,
            h.c.at < day0 + timedelta(days=1),
        )
    ).scalar_one()
    return {
        "wip_lots": int(lots),
        "wip_qty": float(qty),
        "on_hold": int(held),
        "qtime_warn": warn,
        "qtime_exceeded": exceeded,
        "equipment": sorted(states.values(), key=lambda x: str(x["category"])),
        "pm_due": pm_due,
        "pm_warn": pm_warn,
        "track_outs_today": int(moves),
    }
