"""单位换算：基于换算关系图（直接、反向、多跳）；数量精度与计件单位整数校验。

数量统一保留 ``QTY_SCALE``（6）位小数（bom.md §10）；量纲为 ``count`` 的单位
（ea / die / strip / unit / wafer 等计件单位）录入的数量必须是整数。
"""

import uuid
from collections import deque
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES

QTY_SCALE = 6
Edge = tuple[float, float]  # 目标值 = 源值 * factor + offset


_Q = Decimal(1).scaleb(-QTY_SCALE)


def to_qty(v: Any) -> Decimal:
    """数量转 Decimal 并按 ROUND_HALF_UP 保留 6 位小数（D31：浮点误差不入库、不进比对）。

    浮点数按其最短十进制表示（``repr``）转换，如 ``0.1 + 0.2`` → ``0.300000``。
    """
    d = v if isinstance(v, Decimal) else Decimal(repr(float(v)))
    return d.quantize(_Q, rounding=ROUND_HALF_UP)


def round_qty(v: Any) -> float:
    """数量按 :func:`to_qty` 规则四舍五入后的浮点值（用于 JSON 输出与内部比较）。"""
    return float(to_qty(v))


def is_count(session: Session, tid: uuid.UUID, uom_id: Any) -> bool:
    """单位是否为计件单位（量纲 count）。"""
    if not uom_id:
        return False
    t = TABLES["uom"]
    dim = (
        conn(session)
        .execute(sa.select(t.c.dimension).where(t.c.tenant_id == tid, t.c.id == uom_id))
        .scalar()
    )
    return dim == "count"


def is_whole(v: Any) -> bool:
    """按 6 位小数取整后是否为整数。"""
    r = round_qty(v)
    return r == int(r)


def count_errors(
    session: Session, tid: uuid.UUID, uom_id: Any, fields: dict[str, Any]
) -> list[tuple[str, str]]:
    """计件单位下各数量字段须为整数，返回 ``(字段, 信息)`` 错误列表。"""
    if not is_count(session, tid, uom_id):
        return []
    return [
        (k, f"{k}: must be a whole number for a count unit")
        for k, v in fields.items()
        if v is not None and not is_whole(v)
    ]


def convert(
    session: Session, tid: uuid.UUID, src: uuid.UUID, dst: uuid.UUID, value: float
) -> dict[str, Any]:
    """单位换算。

    Args:
        session: 数据库会话。
        tid: 租户 id。
        src: 源单位 id。
        dst: 目标单位 id。
        value: 数值。

    Returns:
        ``{"value": 换算结果, "path": 换算路径}``。

    Raises:
        HTTPException: 无可用换算路径（422）。
    """
    if src == dst:
        return {"value": round_qty(value), "path": [str(src)]}
    t = TABLES["uom_conversion"]
    graph: dict[Any, list[tuple[Any, Edge]]] = {}
    for r in conn(session).execute(sa.select(t).where(t.c.tenant_id == tid)).mappings():
        f, o = float(r["factor"]), float(r["offset"] or 0)
        graph.setdefault(r["from_uom_id"], []).append((r["to_uom_id"], (f, o)))
        graph.setdefault(r["to_uom_id"], []).append((r["from_uom_id"], (1 / f, -o / f)))
    q: deque[tuple[Any, float, list[Any]]] = deque([(src, value, [src])])
    seen = {src}
    while q:
        node, v, path = q.popleft()
        for nxt, (f, o) in graph.get(node, []):
            if nxt in seen:
                continue
            nv = v * f + o
            if nxt == dst:
                return {"value": round_qty(nv), "path": [str(p) for p in [*path, nxt]]}
            seen.add(nxt)
            q.append((nxt, nv, [*path, nxt]))
    raise HTTPException(
        status_code=422, detail="No conversion path between these units"
    )
