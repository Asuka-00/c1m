"""Tiny tenant-scoped query helpers shared by MES modules."""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.core.spec.serialize import to_json

Row = dict[str, Any]


def jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return to_json(v)


# ---------------- tiny query helpers ----------------
def one(s: Session, tid: uuid.UUID, code: str, rid: Any) -> Row | None:
    if rid is None:
        return None
    t = TABLES[code]
    r = (
        conn(s)
        .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.id == rid))
        .mappings()
        .first()
    )
    return dict(r) if r else None


def find(
    s: Session, tid: uuid.UUID, code: str, order: str | None = None, **eq: Any
) -> list[Row]:
    t = TABLES[code]
    stmt = sa.select(t).where(t.c.tenant_id == tid)
    for k, v in eq.items():
        stmt = stmt.where(t.c[k].is_(None) if v is None else t.c[k] == v)
    if order:
        stmt = stmt.order_by(t.c[order])
    return [dict(r) for r in conn(s).execute(stmt).mappings()]
