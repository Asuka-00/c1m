"""CT / Move 报表（D73 + D73/D74/D70 补充，P3-B5）：基于 ``mes_lot_history`` 实时计算。

口径：

* Move：一次出站（``move_out``）算 1 move，``moves`` 为批次数、``move_qty`` 为出站片数；
  拆批、合批、跳站不算。出站工步属于返工路线（``route_type=rework``）时只计入
  ``rework_moves`` / ``rework_move_qty``（T5-1）。普通工步下机带出的返工片
  （履历 ``rework`` 且带 ``unit_id``）计入 ``rework_qty``，只供统计。
* 工序 CT：上一次出站（首工序为开批 ``start``）到本次出站，按本次出站的站点日期归日，
  单位小时，不扣 Hold；子批 / 转换子批起点继承母批在拆分时刻之前的最近起点，合批目标取
  自身与各源批起点中最早的时间。只统计非返工出站。
* ``hold_hours``：同一批出站样本的平均 Hold 时长，Hold 区间截取到该次出站的
  [起点, 出站) 段内，即 Hold 按批次实际停留的工序分摊（T5-3）。
* 在制：``date_to`` 当天站点日末时点的非终态批次（含 Hold，T5-2），按所在工序统计。
* 时长字段为 2 位小数字符串（ROUND_HALF_UP，Decimal 计算，D76），无数据为 null；
  计数为 JSON 整数，无数据为 0。分位数线性插值（同 ``percentile_cont``）。
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.core.spec.excel import tenant_tz
from app.mes.common.sitedate import site_day_bounds
from app.mes.lot.service import TERMINAL

Row = dict[str, Any]
MAX_DAYS = 92
_H = Decimal(3600)
_Q2 = Decimal("0.01")
# 在制时点还原：批次停在哪个工步，看时点之后第一条「在原工步上发生」的履历
_STAY = ("move_in", "track_in", "track_out", "move_out", "hold", "release", "scrap")
# 履历 qty 等于批次数量的动作（scrap / rework 的 qty 是报废 / 返工片数，不用）
_QTY = (
    "start",
    "move_in",
    "track_in",
    "track_out",
    "move_out",
    "hold",
    "release",
    "split",
    "merge",
    "jump",
    "complete",
    "transform",
    "transform_undo",
)
_TERMINAL = tuple(str(x) for x in TERMINAL)


def _rows(s: Session, q: Any) -> list[Row]:
    return [dict(r) for r in conn(s).execute(q).mappings().all()]


def hours(v: Decimal | None) -> str | None:
    """秒数（Decimal）转小时，2 位小数字符串（ROUND_HALF_UP）；None 原样返回。"""
    if v is None:
        return None
    return str((v / _H).quantize(_Q2, rounding=ROUND_HALF_UP))


def _secs(a: datetime, b: datetime) -> Decimal:
    d = b - a
    return Decimal(d.days * 86400 + d.seconds) + Decimal(d.microseconds) / 1_000_000


def _avg(xs: list[Decimal]) -> Decimal | None:
    return sum(xs, Decimal(0)) / len(xs) if xs else None


def percentile(xs: list[Decimal], p: Decimal) -> Decimal | None:
    """线性插值分位数，与 PostgreSQL ``percentile_cont`` 一致；空列表返回 None。"""
    if not xs:
        return None
    v = sorted(xs)
    pos = p * (len(v) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


class _Anchors:
    """批次「上一次出站 / 开批」起点，含拆批、转换继承与合批取最早（懒加载 + 缓存）。"""

    def __init__(self, s: Session, tid: uuid.UUID, end: datetime) -> None:
        self.s, self.tid, self.end = s, tid, end
        self.ev: dict[Any, list[tuple[datetime, str, Any]]] = {}

    def load(self, ids: set[Any]) -> None:
        ids = {i for i in ids if i not in self.ev}
        if not ids:
            return
        for i in ids:
            self.ev[i] = []
        h, g = TABLES["lot_history"], TABLES["lot_genealogy"]
        for r in _rows(
            self.s,
            sa.select(h.c.lot_id, h.c.at).where(
                h.c.tenant_id == self.tid,
                h.c.lot_id.in_(ids),
                h.c.action.in_(("start", "move_out")),
                h.c.at < self.end,
            ),
        ):
            self.ev[r["lot_id"]].append((r["at"], "pos", None))
        for r in _rows(
            self.s,
            sa.select(g.c.parent_lot_id, g.c.child_lot_id, g.c.relation, g.c.at).where(
                g.c.tenant_id == self.tid,
                g.c.child_lot_id.in_(ids),
                g.c.at < self.end,
            ),
        ):
            kind = "merge" if r["relation"] == "merge" else "inherit"
            self.ev[r["child_lot_id"]].append((r["at"], kind, r["parent_lot_id"]))

    def at(self, lot_id: Any, t: datetime, depth: int = 0) -> datetime | None:
        """``lot_id`` 在 ``t`` 之前的最近起点；无法确定时返回 None。"""
        if depth > 50:
            return None
        self.load({lot_id})
        prior = [e for e in self.ev[lot_id] if e[0] < t]
        if not prior:
            return None
        last = max(e[0] for e in prior)
        group = [e for e in prior if e[0] == last]
        if any(k == "pos" for _, k, _ in group):
            return last
        inherit = [p for _, k, p in group if k == "inherit"]
        if inherit:
            return self.at(inherit[0], last, depth + 1)
        srcs = [p for _, k, p in group if k == "merge"]
        self.load(set(srcs))
        cands = [self.at(lot_id, last, depth + 1)] + [
            self.at(p, last, depth + 1) for p in srcs
        ]
        got = [c for c in cands if c is not None]
        return min(got) if got else None


def _bucket() -> Row:
    return {
        "moves": 0,
        "move_qty": 0,
        "rework_moves": 0,
        "rework_move_qty": 0,
        "rework_qty": 0,
        "ct": [],
        "hold": [],
    }


def _out(b: Row, pct: bool) -> Row:
    r = {k: b[k] for k in ("moves", "move_qty", "rework_moves", "rework_move_qty")}
    r["rework_qty"] = b["rework_qty"]
    r["ct_avg_hours"] = hours(_avg(b["ct"]))
    if pct:
        r["ct_p50_hours"] = hours(percentile(b["ct"], Decimal("0.5")))
        r["ct_p90_hours"] = hours(percentile(b["ct"], Decimal("0.9")))
    r["hold_hours"] = hours(_avg(b["hold"]))
    return r


def _filters(stmt: Any, h: Any, lot: Any, op: Any, prod: Any) -> Any:
    if op is not None:
        stmt = stmt.where(h.c.operation_id == op)
    if prod is not None:
        stmt = stmt.where(lot.c.product_id == prod)
    return stmt


def _wip(
    s: Session, tid: uuid.UUID, end: datetime, op: Any, prod: Any
) -> dict[Any, Row]:
    """``end`` 时点各工序在制：``{operation_id: {wip_lots, on_hold_lots, on_hold_qty}}``。"""
    h, lt, rs = TABLES["lot_history"], TABLES["lot"], TABLES["route_step"]
    lots = sa.select(lt.c.id, lt.c.current_step_id).where(lt.c.tenant_id == tid)
    if prod is not None:
        lots = lots.where(lt.c.product_id == prod)
    cur = {r["id"]: r["current_step_id"] for r in _rows(s, lots)}
    if not cur:
        return {}
    ids = list(cur)
    last = {
        r["lot_id"]: r
        for r in _rows(
            s,
            sa.select(h.c.lot_id, h.c.to_status)
            .where(h.c.tenant_id == tid, h.c.lot_id.in_(ids), h.c.at < end)
            .order_by(h.c.lot_id, h.c.at.desc(), h.c.id.desc())
            .distinct(h.c.lot_id),
        )
    }
    alive = [i for i, r in last.items() if r["to_status"] not in _TERMINAL]
    if not alive:
        return {}
    qty = {
        r["lot_id"]: int(r["qty"] or 0)
        for r in _rows(
            s,
            sa.select(h.c.lot_id, h.c.qty)
            .where(
                h.c.tenant_id == tid,
                h.c.lot_id.in_(alive),
                h.c.at < end,
                h.c.action.in_(_QTY),
            )
            .order_by(h.c.lot_id, h.c.at.desc(), h.c.id.desc())
            .distinct(h.c.lot_id),
        )
    }
    nxt = {
        r["lot_id"]: r["route_step_id"]
        for r in _rows(
            s,
            sa.select(h.c.lot_id, h.c.route_step_id)
            .where(
                h.c.tenant_id == tid,
                h.c.lot_id.in_(alive),
                h.c.at >= end,
                h.c.action.in_(_STAY),
                h.c.route_step_id.is_not(None),
            )
            .order_by(h.c.lot_id, h.c.at, h.c.id)
            .distinct(h.c.lot_id),
        )
    }
    step = {i: nxt.get(i) or cur[i] for i in alive}
    sops = {
        r["id"]: r["operation_id"]
        for r in _rows(
            s,
            sa.select(rs.c.id, rs.c.operation_id).where(
                rs.c.tenant_id == tid,
                rs.c.id.in_([x for x in step.values() if x is not None]),
            ),
        )
    }
    lh = TABLES["lot_hold"]
    held = {
        r["lot_id"]
        for r in _rows(
            s,
            sa.select(lh.c.lot_id).where(
                lh.c.tenant_id == tid,
                lh.c.lot_id.in_(alive),
                lh.c.held_at < end,
                sa.or_(lh.c.released_at.is_(None), lh.c.released_at >= end),
            ),
        )
    }
    out: dict[Any, Row] = {}
    for i in alive:
        o = sops.get(step[i])
        if o is None or (op is not None and o != op):
            continue
        w = out.setdefault(o, {"wip_lots": 0, "on_hold_lots": 0, "on_hold_qty": 0})
        w["wip_lots"] += 1
        if i in held:
            w["on_hold_lots"] += 1
            w["on_hold_qty"] += qty.get(i, 0)
    return out


def ct_move(
    s: Session,
    tid: uuid.UUID,
    date_from: date,
    date_to: date,
    operation_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
) -> Row:
    """CT / Move 报表（D73）。参数已校验；返回契约形状（见模块说明）。"""
    tz = tenant_tz(s, tid)
    n = (date_to - date_from).days + 1
    start, end = site_day_bounds(s, tid, date_from, n)
    h, lt, rs, rt = (
        TABLES["lot_history"],
        TABLES["lot"],
        TABLES["route_step"],
        TABLES["route"],
    )
    base = (
        sa.select(
            h.c.lot_id,
            h.c.action,
            h.c.at,
            h.c.qty,
            h.c.operation_id,
            rt.c.route_type,
        )
        .select_from(
            h.join(lt, lt.c.id == h.c.lot_id)
            .outerjoin(rs, rs.c.id == h.c.route_step_id)
            .outerjoin(rt, rt.c.id == rs.c.route_id)
        )
        .where(
            h.c.tenant_id == tid,
            h.c.at >= start,
            h.c.at < end,
            sa.or_(
                h.c.action == "move_out",
                sa.and_(h.c.action == "rework", h.c.unit_id.is_not(None)),
            ),
        )
        .order_by(h.c.at, h.c.id)
    )
    rows = _rows(s, _filters(base, h, lt, operation_id, product_id))
    days = {(date_from + timedelta(days=i)).isoformat(): _bucket() for i in range(n)}
    ops: dict[Any, Row] = defaultdict(_bucket)
    total = _bucket()
    anchors = _Anchors(s, tid, end)
    normal = [
        r for r in rows if r["action"] == "move_out" and r["route_type"] != "rework"
    ]
    anchors.load({r["lot_id"] for r in normal})
    lh = TABLES["lot_hold"]
    holds: dict[Any, list[tuple[datetime, datetime | None]]] = defaultdict(list)
    if normal:
        for r in _rows(
            s,
            sa.select(lh.c.lot_id, lh.c.held_at, lh.c.released_at).where(
                lh.c.tenant_id == tid,
                lh.c.lot_id.in_({x["lot_id"] for x in normal}),
                lh.c.held_at < end,
                lh.c.held_at.is_not(None),
            ),
        ):
            holds[r["lot_id"]].append((r["held_at"], r["released_at"]))
    for r in rows:
        day = r["at"].astimezone(tz).date().isoformat()
        q = int(r["qty"] or 0)
        bs = (days[day], ops[r["operation_id"]], total)
        if r["action"] == "rework":
            if r["route_type"] == "rework":
                continue
            for b in bs:
                b["rework_qty"] += q
            continue
        if r["route_type"] == "rework":
            for b in bs:
                b["rework_moves"] += 1
                b["rework_move_qty"] += q
            continue
        for b in bs:
            b["moves"] += 1
            b["move_qty"] += q
        a = anchors.at(r["lot_id"], r["at"])
        if a is None:
            continue
        ct = _secs(a, r["at"])
        hold = Decimal(0)
        for ha, hb in holds.get(r["lot_id"], []):
            lo, hi = max(ha, a), min(hb or r["at"], r["at"])
            if hi > lo:
                hold += _secs(lo, hi)
        for b in bs:
            b["ct"].append(ct)
            b["hold"].append(hold)
    wip = _wip(s, tid, end, operation_id, product_id)
    keys = {k for k, b in ops.items() if b["moves"] or b["rework_moves"]} | set(wip)
    keys.discard(None)
    by_op: list[Row] = []
    if keys:
        ot = TABLES["operation"]
        info = {
            r["id"]: r
            for r in _rows(
                s,
                sa.select(ot.c.id, ot.c.code, ot.c.name).where(
                    ot.c.tenant_id == tid, ot.c.id.in_(keys)
                ),
            )
        }
        seq = {
            r["operation_id"]: r["seq"]
            for r in _rows(
                s,
                sa.select(rs.c.operation_id, sa.func.min(rs.c.seq).label("seq"))
                .select_from(rs.join(rt, rt.c.id == rs.c.route_id))
                .where(
                    rs.c.tenant_id == tid,
                    rs.c.operation_id.in_(keys),
                    rt.c.route_type == "main",
                )
                .group_by(rs.c.operation_id),
            )
        }
        for k in keys:
            o = info.get(k) or {}
            w = wip.get(k) or {"wip_lots": 0, "on_hold_lots": 0, "on_hold_qty": 0}
            by_op.append(
                {
                    "operation_id": str(k),
                    "operation": o.get("code"),
                    "operation_name": o.get("name"),
                    **_out(ops[k] if k in ops else _bucket(), True),
                    **w,
                    "_seq": seq.get(k),
                }
            )
        by_op.sort(
            key=lambda r: (
                r["_seq"] is None,
                r["_seq"] or 0,
                r["operation"] or "",
                r["operation_id"],
            )
        )
        for r in by_op:
            del r["_seq"]
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "timezone": tz.key,
        "trend": [{"day": d, **_out(b, False)} for d, b in days.items()],
        "by_operation": by_op,
        "total": _out(total, False),
    }
