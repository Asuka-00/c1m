"""Generic tenant-scoped queries: list/filter/search/sort, get, all rows, tree."""

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import Row, conn, table
from app.core.spec.engine import (
    Entity,
)
from app.core.spec.errors import http_422
from app.core.spec.serialize import coerce, serialize


# ---------------- queries ----------------
def sortable(e: Entity) -> dict[str, Any]:
    t = table(e)
    out = {
        f.name: t.c[f.column]
        for f in e.all_fields
        if f.type not in ("json", "ref", "text")
    }
    for c in ("created_at", "updated_at", "version", "status"):
        if c in t.c:
            out[c] = t.c[c]
    return out


def base_select(e: Entity, tenant_id: uuid.UUID) -> sa.Select[Any]:
    t = table(e)
    return sa.select(t).where(t.c.tenant_id == tenant_id)


def apply_filters(
    e: Entity, stmt: sa.Select[Any], filters: dict[str, str]
) -> sa.Select[Any]:
    t = table(e)
    for name, raw in filters.items():
        if name == "status" and e.versioned:
            stmt = stmt.where(t.c.status == raw)
            continue
        f = e.field(name) or next((x for x in e.all_fields if x.column == name), None)
        if not f or f.type in ("json", "text"):
            continue
        if f.type == "ref" and raw == "null":
            stmt = stmt.where(t.c[f.column].is_(None))
            continue
        try:
            v = coerce(f, raw)
        except ValueError as ex:
            raise http_422([(name, f"{name} {ex}")]) from ex
        stmt = stmt.where(t.c[f.column] == v)
    return stmt


def search(e: Entity, stmt: sa.Select[Any], q: str | None) -> sa.Select[Any]:
    if not q:
        return stmt
    t = table(e)
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    cols = [t.c[f.column] for f in e.all_fields if f.search]
    if not cols:
        return stmt
    return stmt.where(sa.or_(*(c.ilike(f"%{esc}%", escape="\\") for c in cols)))


def list_rows(
    session: Session,
    e: Entity,
    tenant_id: uuid.UUID,
    *,
    q: str | None,
    filters: dict[str, str],
    sort_by: str | None,
    sort_order: str,
    offset: int,
    limit: int,
) -> tuple[list[Row], int]:
    t = table(e)
    stmt = search(e, apply_filters(e, base_select(e, tenant_id), filters), q)
    c = conn(session)
    count = c.execute(
        sa.select(sa.func.count()).select_from(stmt.subquery())
    ).scalar_one()
    cols = sortable(e)
    key = sort_by or e.sort_default
    if key not in cols:
        raise HTTPException(
            status_code=422, detail=f"sort_by must be one of: {', '.join(sorted(cols))}"
        )
    order = sort_order if sort_by else ("desc" if key in ("created_at",) else "asc")
    col = cols[key]
    stmt = stmt.order_by(
        col.desc().nulls_last() if order == "desc" else col.asc().nulls_last(),
        *([t.c.version] if e.versioned else []),
        t.c.id,
    )
    rows = [dict(r) for r in c.execute(stmt.offset(offset).limit(limit)).mappings()]
    return rows, int(count)


def get_row(session: Session, e: Entity, tenant_id: uuid.UUID, rid: uuid.UUID) -> Row:
    t = table(e)
    r = (
        conn(session)
        .execute(base_select(e, tenant_id).where(t.c.id == rid))
        .mappings()
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    return dict(r)


def all_rows(
    session: Session, e: Entity, tenant_id: uuid.UUID, limit: int = 5000
) -> list[Row]:
    t = table(e)
    stmt = base_select(e, tenant_id).order_by(
        t.c[sortable(e).get(e.sort_default, t.c.id).name], t.c.id
    )
    return [dict(r) for r in conn(session).execute(stmt.limit(limit)).mappings()]


def tree(session: Session, tenant_id: uuid.UUID, e: Entity) -> list[Row]:
    if not e.tree:
        raise HTTPException(status_code=404, detail="Entity is not hierarchical")
    rows = serialize(session, tenant_id, e, all_rows(session, e, tenant_id))
    by_parent: dict[Any, list[Row]] = {}
    for r in rows:
        by_parent.setdefault(r.get("parent_id"), []).append(r)

    def build(pid: Any) -> list[Row]:
        return [{**r, "children": build(r["id"])} for r in by_parent.get(pid, [])]

    return build(None)
