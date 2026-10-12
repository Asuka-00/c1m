"""Demo dataset engine: rows are collected with add() by every module's demo.py."""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session, select

from app.core.spec.base import conn
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.serialize import coerce
from app.core.tenant import set_tenant
from app.platform.tenants.models import Tenant

Ref = tuple[str, str]  # (entity, natural key "CODE" / "CODE@v")
DEMO: list[tuple[str, dict[str, Any]]] = []
ACTIVATE: list[Ref] = []


def _rows(rows: list[Any]) -> list[Any]:
    """Heterogeneous literal tables (keeps the type checker out of the data)."""
    return rows


def add(entity: str, **values: Any) -> None:
    DEMO.append((entity, values))


# ---------------- helpers ----------------
def _resolve(session: Session, tid: uuid.UUID, ref: Ref) -> Any:
    ent, key = ref
    if ent == "route_step":  # "ROUTE@v#seq"
        rkey, _, seq = key.partition("#")
        st = TABLES["route_step"]
        rid = _resolve(session, tid, ("route", rkey))
        return (
            conn(session)
            .execute(
                sa.select(st.c.id).where(st.c.route_id == rid, st.c.seq == int(seq))
            )
            .scalar()
        )
    e = ENTITIES[ent]
    t = TABLES[ent]
    code, _, ver = key.partition("@")
    col = t.c.code if e.has_code else t.c[e.label_field]
    stmt = sa.select(t.c.id).where(t.c.tenant_id == tid, col == code)
    if e.versioned:
        stmt = stmt.where(t.c.version == int(ver or 1))
    return conn(session).execute(stmt).scalar()


def _exists(
    session: Session,
    tid: uuid.UUID,
    ent: str,
    values: dict[str, Any],
    refs: dict[str, Any],
) -> bool:
    e = ENTITIES[ent]
    t = TABLES[ent]
    stmt = sa.select(t.c.id).where(t.c.tenant_id == tid)
    for k in e.natural_key:
        f = e.field(k)
        if k == "version":
            stmt = stmt.where(t.c.version == int(values.get("version") or 1))
        elif f:
            v = refs.get(k) if f.type == "ref" else coerce(f, values.get(k))
            col = t.c[f.column]
            stmt = stmt.where(col.is_(None) if v is None else col == v)
    return conn(session).execute(stmt).first() is not None


def default_tenant(session: Session) -> uuid.UUID:
    t = session.exec(select(Tenant).where(Tenant.slug == "default")).one()
    set_tenant(session, t.id)
    return t.id
