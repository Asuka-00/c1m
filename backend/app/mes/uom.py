"""UOM conversion over the conversion graph (direct, inverse, multi-hop)."""

import uuid
from collections import deque
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.engine import TABLES
from app.core.spec.service import conn

Edge = tuple[float, float]  # to = from * factor + offset


def convert(
    session: Session, tid: uuid.UUID, src: uuid.UUID, dst: uuid.UUID, value: float
) -> dict[str, Any]:
    if src == dst:
        return {"value": value, "path": [str(src)]}
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
                return {"value": nv, "path": [str(p) for p in [*path, nxt]]}
            seen.add(nxt)
            q.append((nxt, nv, [*path, nxt]))
    raise HTTPException(
        status_code=422, detail="No conversion path between these units"
    )
