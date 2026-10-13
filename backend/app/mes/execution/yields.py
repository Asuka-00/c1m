"""良率统计：按工序 / 产品 / 批次统计良品与报废，报废原因帕累托。

良率 = 良品数 / (良品数 + 报废数)；良品数取统计区间内各次下机后的批次数量，
报废数取同区间的报废履历（下机报废与在制报废）。
"""

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Literal

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.mes.common.query import one

Row = dict[str, Any]
Group = Literal["operation", "product", "lot"]


def yield_report(
    s: Session, tid: uuid.UUID, start: datetime, end: datetime, group: Group
) -> Row:
    """良率统计。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        start: 区间开始。
        end: 区间结束。
        group: 分组维度（operation / product / lot）。

    Returns:
        ``{rows: [{key, name, good, scrap, yield}], pareto: [{reason, name, qty, pct, cum_pct}], total}``。
    """
    h, lot = TABLES["lot_history"], TABLES["lot"]
    q = (
        sa.select(
            h.c.action,
            h.c.qty,
            h.c.reason_id,
            h.c.operation_id,
            h.c.lot_id,
            lot.c.code.label("lot_code"),
            lot.c.product_id,
        )
        .join(lot, lot.c.id == h.c.lot_id)
        .where(
            h.c.tenant_id == tid,
            h.c.at >= start,
            h.c.at < end,
            h.c.action.in_(["track_out", "scrap"]),
        )
    )
    cache: dict[tuple[str, Any], Row | None] = {}

    def get(e: str, rid: Any) -> Row | None:
        if (e, rid) not in cache:
            cache[(e, rid)] = one(s, tid, e, rid) if rid else None
        return cache[(e, rid)]

    def key(r: Any) -> tuple[str, str]:
        if group == "lot":
            return r.lot_code, r.lot_code
        e, rid = (
            ("operation", r.operation_id)
            if group == "operation"
            else (
                "product",
                r.product_id,
            )
        )
        x = get(e, rid)
        return (x["code"], x["name"]) if x else ("—", "—")

    agg: dict[str, Row] = {}
    reasons: dict[Any, int] = defaultdict(int)
    for r in conn(s).execute(q):
        k, name = key(r)
        a = agg.setdefault(k, {"key": k, "name": name, "good": 0, "scrap": 0})
        n = r.qty or 0
        if r.action == "track_out":
            a["good"] += n
        else:
            a["scrap"] += n
            reasons[r.reason_id] += n
    rows = []
    for a in agg.values():
        tot = a["good"] + a["scrap"]
        rows.append({**a, "yield": round(a["good"] / tot, 4) if tot else None})
    rows.sort(key=lambda x: (x["yield"] if x["yield"] is not None else 2, x["key"]))
    total = sum(reasons.values())
    pareto, cum = [], 0
    for rid, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        rc = get("reason_code", rid)
        cum += n
        pareto.append(
            {
                "reason": rc["code"] if rc else "—",
                "name": rc["name"] if rc else "—",
                "qty": n,
                "pct": round(n / total, 4),
                "cum_pct": round(cum / total, 4),
            }
        )
    good = sum(a["good"] for a in agg.values())
    return {
        "rows": rows,
        "pareto": pareto,
        "total": {
            "good": good,
            "scrap": total,
            "yield": round(good / (good + total), 4) if good + total else None,
        },
    }
