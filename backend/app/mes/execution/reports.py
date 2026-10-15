"""WIP 看板与报表：在制分布 / 滞留、产出与报废日报、设备 OEE。

OEE = 时间稼动率 × 性能稼动率 × 良品率：

* 时间稼动率 = PRD 时间 / 负荷时间（统计区间扣除 NST 非排产时间），由 E10 状态履历还原；
* 性能稼动率 = 理论加工时间 / PRD 时间，理论时间 = Σ 加工数 / 理论 UPH
  （配方设备映射的 UPH 优先，其次设备 UPH；区间内任一次下机缺少 UPH 时不计算）；
* 良品率 = 良品数 / (良品数 + 报废数)，按该设备上的下机与报废履历统计。
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.models import iso_utc
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.mes.common.query import find, one
from app.mes.equipment.service import e10_current
from app.mes.lot.service import TERMINAL

Row = dict[str, Any]


def r3(v: float | None) -> float | None:
    """比例保留 4 位小数（None 原样返回）。"""
    return None if v is None else round(v, 4)


def _rows(s: Session, q: Any) -> list[Row]:
    return [dict(r) for r in conn(s).execute(q).mappings().all()]


def wip_summary(
    s: Session,
    tid: uuid.UUID,
    *,
    product_id: uuid.UUID | None = None,
    lot_type_id: uuid.UUID | None = None,
    route_id: uuid.UUID | None = None,
) -> Row:
    """在制看板：按状态 / 工步 / 产品分布、Hold 数、滞留时间最长的批次。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        product_id: 仅统计该产品。
        lot_type_id: 仅统计该批次类型。
        route_id: 仅统计当前工步属于该工艺路线的批次。

    Returns:
        ``{total_lots, total_qty, on_hold, by_status, by_step, by_product, aging}``。
    """
    t = TABLES["lot"]
    stmt = sa.select(t).where(t.c.tenant_id == tid, t.c.lot_status.not_in(TERMINAL))
    if product_id:
        stmt = stmt.where(t.c.product_id == product_id)
    if lot_type_id:
        stmt = stmt.where(t.c.lot_type_id == lot_type_id)
    if route_id:
        rs = TABLES["route_step"]
        stmt = stmt.where(
            t.c.current_step_id.in_(
                sa.select(rs.c.id).where(
                    rs.c.tenant_id == tid, rs.c.route_id == route_id
                )
            )
        )
    lots = _rows(s, stmt)
    h = TABLES["lot_history"]
    last = {
        r["lot_id"]: r["at"]
        for r in _rows(
            s,
            sa.select(h.c.lot_id, sa.func.max(h.c.at).label("at"))
            .where(h.c.tenant_id == tid)
            .group_by(h.c.lot_id),
        )
    }
    at = now()
    by_status: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_step: dict[Any, Row] = {}
    by_product: dict[Any, Row] = {}
    aging: list[Row] = []
    for lot in lots:
        q = int(lot["qty"] or 0)
        st = by_status[lot["lot_status"]]
        st[0] += 1
        st[1] += q
        step = one(s, tid, "route_step", lot["current_step_id"])
        k = step and step["id"]
        if k not in by_step:
            op = step and one(s, tid, "operation", step["operation_id"])
            by_step[k] = {
                "step_seq": step and step["seq"],
                "operation": op and op["code"],
                "route": step
                and (one(s, tid, "route", step["route_id"]) or {}).get("code"),
                "lots": 0,
                "qty": 0,
                "on_hold": 0,
            }
        by_step[k]["lots"] += 1
        by_step[k]["qty"] += q
        by_step[k]["on_hold"] += int(bool(lot["on_hold"]))
        pk = lot["product_id"]
        if pk not in by_product:
            pr = one(s, tid, "product", pk)
            by_product[pk] = {
                "product_id": pk and str(pk),
                "product": pr and pr["code"],
                "lots": 0,
                "qty": 0,
            }
        by_product[pk]["lots"] += 1
        by_product[pk]["qty"] += q
        since = last.get(lot["id"]) or lot.get("created_at")
        aging.append(
            {
                "id": str(lot["id"]),
                "lot": lot["code"],
                "status": lot["lot_status"],
                "on_hold": bool(lot["on_hold"]),
                "step_seq": step and step["seq"],
                "qty": q,
                "since": since and iso_utc(since),
                "hours": since and round((at - since).total_seconds() / 3600, 1),
            }
        )
    aging.sort(key=lambda r: -float(r["hours"] or 0))
    return {
        "total_lots": len(lots),
        "total_qty": sum(int(x["qty"] or 0) for x in lots),
        "on_hold": sum(1 for x in lots if x["on_hold"]),
        "by_status": [
            {"status": k, "lots": v[0], "qty": v[1]} for k, v in by_status.items()
        ],
        "by_step": sorted(
            by_step.values(),
            key=lambda r: (str(r["route"]), r["step_seq"] or 0),
        ),
        "by_product": sorted(by_product.values(), key=lambda r: -r["qty"]),
        "aging": aging[:20],
    }


def daily_output(
    s: Session, tid: uuid.UUID, start: datetime, end: datetime
) -> list[Row]:
    """产出日报：按日统计出站次数 / 数量、报废数、完工批次数（服务器时区日期）。"""
    h = TABLES["lot_history"]
    rows = _rows(
        s,
        sa.select(h.c.action, h.c.qty, h.c.at, h.c.to_status).where(
            h.c.tenant_id == tid,
            h.c.at >= start,
            h.c.at < end,
            h.c.action.in_(("move_out", "scrap")),
        ),
    )
    days: dict[str, Row] = {}
    d = start.date()
    while d < end.date() or (d == end.date() and end.time() != datetime.min.time()):
        days[d.isoformat()] = {
            "day": d.isoformat(),
            "moves": 0,
            "move_qty": 0,
            "scrap_qty": 0,
            "completed": 0,
        }
        d += timedelta(days=1)
    for r in rows:
        k = r["at"].astimezone(start.tzinfo).date().isoformat()
        x = days.setdefault(
            k, {"day": k, "moves": 0, "move_qty": 0, "scrap_qty": 0, "completed": 0}
        )
        if r["action"] == "move_out":
            x["moves"] += 1
            x["move_qty"] += int(r["qty"] or 0)
            x["completed"] += int(r["to_status"] == "completed")
        else:
            x["scrap_qty"] += int(r["qty"] or 0)
    return sorted(days.values(), key=lambda r: r["day"])


def _segments(
    s: Session, tid: uuid.UUID, eq: Row, start: datetime, end: datetime
) -> list[tuple[Row | None, float]]:
    """区间内设备 E10 状态段 ``[(状态, 秒数)]``（由状态履历还原）。"""
    h = TABLES["e10_history"]
    before = _rows(
        s,
        sa.select(h.c.to_state_id)
        .where(h.c.tenant_id == tid, h.c.equipment_id == eq["id"], h.c.at <= start)
        .order_by(h.c.at.desc())
        .limit(1),
    )
    ch = _rows(
        s,
        sa.select(h.c.to_state_id, h.c.from_state_id, h.c.at)
        .where(
            h.c.tenant_id == tid,
            h.c.equipment_id == eq["id"],
            h.c.at > start,
            h.c.at < end,
        )
        .order_by(h.c.at),
    )
    if before:
        cur = one(s, tid, "e10_state", before[0]["to_state_id"])
    elif ch and ch[0]["from_state_id"]:
        cur = one(s, tid, "e10_state", ch[0]["from_state_id"])
    else:
        cur = e10_current(s, tid, eq) if not ch else None
    out, t0 = [], start
    for c in ch:
        out.append((cur, (c["at"] - t0).total_seconds()))
        cur, t0 = one(s, tid, "e10_state", c["to_state_id"]), c["at"]
    out.append((cur, (end - t0).total_seconds()))
    return out


def oee(s: Session, tid: uuid.UUID, start: datetime, end: datetime) -> list[Row]:
    """设备 OEE（主设备，统计区间 ``[start, end)``，见模块说明）。

    Returns:
        每台设备 ``{equipment, hours: {E10 类别: 小时}, loading_h, prd_h,
        availability, performance, quality, oee, good, scrap, uph_missing}``；
        无法计算的指标为 None。
    """
    end = min(end, now())
    h = TABLES["lot_history"]
    out = []
    wcs = {w["id"]: w["code"] for w in find(s, tid, "workcenter")}
    for eq in find(s, tid, "equipment", order="code", unit_kind="main"):
        cats: dict[str, float] = defaultdict(float)
        for st, sec in _segments(s, tid, eq, start, end):
            cats[(st or {}).get("e10_category") or "UNK"] += sec
        total = sum(cats.values())
        loading = total - cats.get("NST", 0.0)
        prd = cats.get("PRD", 0.0)
        hist = _rows(
            s,
            sa.select(h.c.action, h.c.qty, h.c.recipe_id).where(
                h.c.tenant_id == tid,
                h.c.equipment_id == eq["id"],
                h.c.at >= start,
                h.c.at < end,
                h.c.action.in_(("track_out", "scrap")),
            ),
        )
        good = sum(int(r["qty"] or 0) for r in hist if r["action"] == "track_out")
        scrap = sum(int(r["qty"] or 0) for r in hist if r["action"] == "scrap")
        ideal, missing = 0.0, False
        for r in hist:
            if r["action"] != "track_out":
                continue
            m = (
                find(
                    s,
                    tid,
                    "recipe_equipment",
                    recipe_id=r["recipe_id"],
                    equipment_id=eq["id"],
                )
                if r["recipe_id"]
                else []
            )
            uph = (m[0]["ideal_uph"] if m else None) or eq.get("ideal_uph")
            if not uph:
                missing = True
                continue
            ideal += (int(r["qty"] or 0)) / float(uph) * 3600
        # 报废数计入加工数（按设备 UPH 估算）
        if scrap and eq.get("ideal_uph"):
            ideal += scrap / float(eq["ideal_uph"]) * 3600
        elif scrap:
            missing = True
        avail = prd / loading if loading > 0 else None
        perf = (
            min(ideal / prd, 1.5)
            if prd > 0 and not missing and (good + scrap)
            else None
        )
        qual = good / (good + scrap) if good + scrap else None
        oee_v = (
            avail * perf * qual
            if avail is not None and perf is not None and qual is not None
            else None
        )
        out.append(
            {
                "id": str(eq["id"]),
                "equipment": eq["code"],
                "name": eq["name"],
                "workcenter": wcs.get(eq.get("workcenter_id")),
                "hours": {k: round(v / 3600, 2) for k, v in cats.items()},
                "loading_h": round(loading / 3600, 2),
                "prd_h": round(prd / 3600, 2),
                "availability": r3(avail),
                "performance": r3(perf),
                "quality": r3(qual),
                "oee": r3(oee_v),
                "good": good,
                "scrap": scrap,
                "uph_missing": missing,
            }
        )
    return out


def oee_trend(
    s: Session,
    tid: uuid.UUID,
    start: datetime,
    end: datetime,
    workcenter: str | None = None,
) -> list[Row]:
    """OEE 日趋势：逐日汇总各主设备（可按工作中心过滤）的时间稼动率、良品率与 OEE。

    时间稼动率 = ΣPRD / Σ负荷时间；良品率 = Σ良品 / Σ(良品 + 报废)；
    OEE 为当日可计算设备按负荷时间加权的平均值。

    Returns:
        每日 ``{day, availability, quality, oee, loading_h}``。
    """
    out: list[Row] = []
    day = start
    while day < min(end, now()):
        nxt = day + timedelta(days=1)
        rows = [
            r
            for r in oee(s, tid, day, nxt)
            if not workcenter or r["workcenter"] == workcenter
        ]
        load = sum(r["loading_h"] for r in rows)
        prd = sum(r["prd_h"] for r in rows)
        good = sum(r["good"] for r in rows)
        scrap = sum(r["scrap"] for r in rows)
        ow = [(r["oee"], r["loading_h"]) for r in rows if r["oee"] is not None]
        wsum = sum(w for _, w in ow)
        out.append(
            {
                "day": day.date().isoformat(),
                "availability": r3(prd / load if load else None),
                "quality": r3(good / (good + scrap) if good + scrap else None),
                "oee": r3(sum(v * w for v, w in ow) / wsum if wsum else None),
                "loading_h": round(load, 2),
            }
        )
        day = nxt
    return out
