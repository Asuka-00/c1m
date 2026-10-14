"""通用租户范围查询：列表 / 筛选 / 搜索 / 排序、单行、全部行、树。"""

import uuid
from datetime import timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import Row, conn, table
from app.core.spec.engine import (
    Entity,
)
from app.core.spec.errors import err_422, query_422
from app.core.spec.qdates import parse_date, parse_datetime
from app.core.spec.serialize import coerce, serialize


# ---------------- queries ----------------
def sortable(e: Entity) -> dict[str, Any]:
    """实体允许排序的 ``{名称: 列}``。"""
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


def default_order(e: Entity, key: str) -> str:
    """默认排序方向：时间 / 日期类字段（含 created_at）默认降序（最新在前），其它升序。"""
    f = e.field(key)
    return (
        "desc"
        if key == "created_at" or (f and f.type in ("date", "datetime"))
        else "asc"
    )


def base_select(e: Entity, tenant_id: uuid.UUID) -> sa.Select[Any]:
    """租户范围内的基础查询。"""
    t = table(e)
    return sa.select(t).where(t.c.tenant_id == tenant_id)


def apply_filters(
    e: Entity, stmt: sa.Select[Any], filters: dict[str, str]
) -> sa.Select[Any]:
    """按字段等值 / 引用 id / 状态等条件过滤。"""
    t = table(e)
    bounds: dict[str, dict[str, Any]] = {}
    for name, raw in filters.items():
        if name == "status" and e.versioned:
            stmt = stmt.where(t.c.status == raw)
            continue
        f = e.field(name) or next((x for x in e.all_fields if x.column == name), None)
        if not f and name == "id":
            try:
                ids = [uuid.UUID(x) for x in raw.split(",") if x]
            except ValueError as ex:
                raise query_422([("id", "id: invalid uuid")]) from ex
            stmt = stmt.where(t.c.id.in_(ids))
            continue
        if not f and name.startswith("has_"):
            # has_<字段>=true|false：非空 / 为空（如 alarm_code ?has_migration_note=true）
            g = e.field(name[4:])
            if g and raw.lower() in ("true", "false", "1", "0"):
                col = t.c[g.column]
                yes = raw.lower() in ("true", "1")
                stmt = stmt.where(col.is_not(None) if yes else col.is_(None))
                continue
            raise query_422([(name, f"{name}: must be true or false")])
        if not f and name.endswith(("_from", "_to")):
            stmt = _range(e, stmt, name, raw, bounds)
            continue
        if not f or f.type in ("json", "text"):
            continue
        if f.type == "ref" and raw == "null":
            stmt = stmt.where(t.c[f.column].is_(None))
            continue
        if f.type == "date":  # D77 补充二：等值筛选同样只收严格 YYYY-MM-DD
            d = parse_date(name, raw)
            if d is not None:
                stmt = stmt.where(t.c[f.column] == d)
            continue
        if f.type == "datetime":  # D85：等值筛选同 _from/_to，走 qdates
            dt = parse_datetime(name, raw)
            if dt is not None:
                stmt = stmt.where(t.c[f.column] == dt)
            continue
        try:
            v = coerce(f, raw)
        except ValueError as ex:
            raise query_422([(name, f"{name} {ex}")]) from ex
        stmt = stmt.where(t.c[f.column] == v)
    for base, b in bounds.items():
        if "from" in b and "to" in b and b["from"] > b["to"]:
            raise err_422(
                ["query", f"{base}_from"],
                f"{base}_from is after {base}_to",
                "value_error",
                {"reason": "range_inverted"},
            )
    return stmt


def _range(
    e: Entity,
    stmt: sa.Select[Any],
    name: str,
    raw: str,
    bounds: dict[str, dict[str, Any]] | None = None,
) -> sa.Select[Any]:
    """时间 / 日期范围筛选（D77）。

    - datetime 字段（含 ``created_at``）：半开区间 ``[_from, _to)``，``_to`` 那一刻不含。
    - date 字段：闭区间 ``[_from, _to]``，实现为 ``< _to + 1 天``。
    - datetime 取值必须带偏移（``Z`` 或 ``±hh:mm``），只给日期或无偏移
      → 422 ``timezone_required``（D77 补充一）。
    - 同一字段 ``_from`` 晚于 ``_to`` → 422 ``value_error``，``ctx.reason=range_inverted``
      （由 :func:`apply_filters` 在两端都解析后判断）。
    - date 取值必须严格为 ``YYYY-MM-DD``，其它任何写法 → 422 ``value_error``，
      ``ctx.reason=pattern``；datetime 无法解析同样 ``pattern``（见 :mod:`qdates`）。

    其它名称忽略。
    """
    t = table(e)
    base, bound = name.rsplit("_", 1)
    f = e.field(base) or next((x for x in e.all_fields if x.column == base), None)
    kind = f.type if f else ("datetime" if base == "created_at" else None)
    col = base if f is None else f.column
    if kind not in ("date", "datetime") or col not in t.c:
        return stmt
    v: Any = parse_date(name, raw) if kind == "date" else parse_datetime(name, raw)
    if v is None:
        return stmt
    if bounds is not None:
        bounds.setdefault(base, {})[bound] = v
    c = t.c[col]
    if bound == "from":
        return stmt.where(c >= v)
    return stmt.where(c < (v + timedelta(days=1) if kind == "date" else v))


def search(e: Entity, stmt: sa.Select[Any], q: str | None) -> sa.Select[Any]:
    """按实体文本字段做不区分大小写的模糊搜索。"""
    if not q:
        return stmt
    t = table(e)
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    cols = [t.c[f.column] for f in e.all_fields if f.search]
    exact = [t.c[f.column] for f in e.all_fields if f.search_exact]
    if not cols and not exact:
        return stmt
    return stmt.where(
        sa.or_(
            *(c.ilike(f"%{esc}%", escape="\\") for c in cols),
            *(sa.func.upper(c) == sa.func.upper(sa.literal(q.strip())) for c in exact),
        )
    )


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
    """分页查询实体行。

    Returns:
        ``(当前页行, 过滤后总数)``。
    """
    t = table(e)
    stmt = search(e, apply_filters(e, base_select(e, tenant_id), filters), q)
    c = conn(session)
    count = c.execute(
        sa.select(sa.func.count()).select_from(stmt.subquery())
    ).scalar_one()
    cols = sortable(e)
    key = sort_by or e.sort_default
    if key not in cols:
        raise query_422(
            [("sort_by", f"sort_by must be one of: {', '.join(sorted(cols))}")]
        )
    order = sort_order if sort_by else default_order(e, key)
    col = cols[key]
    stmt = stmt.order_by(
        col.desc().nulls_last() if order == "desc" else col.asc().nulls_last(),
        *([t.c.version] if e.versioned else []),
        t.c.id,
    )
    rows = [dict(r) for r in c.execute(stmt.offset(offset).limit(limit)).mappings()]
    return rows, int(count)


def get_row(session: Session, e: Entity, tenant_id: uuid.UUID, rid: uuid.UUID) -> Row:
    """读取单行。

    Raises:
        HTTPException: 行不存在或不属于当前租户（404）。
    """
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
    session: Session,
    e: Entity,
    tenant_id: uuid.UUID,
    limit: int = 5000,
    *,
    q: str | None = None,
    filters: dict[str, str] | None = None,
) -> list[Row]:
    """读取全部行（带上限，用于选项与导出；可按关键字 / 筛选过滤，约定同列表）。"""
    t = table(e)
    stmt = base_select(e, tenant_id)
    if filters:
        stmt = apply_filters(e, stmt, filters)
    if q:
        stmt = search(e, stmt, q)
    stmt = stmt.order_by(t.c[sortable(e).get(e.sort_default, t.c.id).name], t.c.id)
    return [dict(r) for r in conn(session).execute(stmt.limit(limit)).mappings()]


def distinct_values(
    session: Session,
    e: Entity,
    tenant_id: uuid.UUID,
    name: str,
    q: str | None = None,
    limit: int = 50,
) -> list[str]:
    """文本型筛选字段的去重取值（用于下拉筛选选项，可按关键字模糊匹配）。

    仅允许声明了 ``filter=True`` 的 str 字段，其它字段返回 422。
    """
    f = e.field(name)
    if not f or f.type != "str" or not f.filterable:
        raise err_422(
            ["path", "field"],
            f"{name} is not a text filter",
            "not_text_filter",
            {"field": name},
        )
    sub = base_select(e, tenant_id).subquery()
    stmt = sa.select(sub.c[f.column]).where(sub.c[f.column].is_not(None)).distinct()
    if q:
        stmt = stmt.where(sub.c[f.column].ilike(f"%{q}%"))
    stmt = stmt.order_by(sub.c[f.column]).limit(limit)
    return [r[0] for r in conn(session).execute(stmt)]


def tree(session: Session, tenant_id: uuid.UUID, e: Entity) -> list[Row]:
    """以嵌套 children 形式返回树形实体的全部节点。"""
    if not e.tree:
        raise HTTPException(status_code=404, detail="Entity is not hierarchical")
    rows = serialize(session, tenant_id, e, all_rows(session, e, tenant_id))
    by_parent: dict[Any, list[Row]] = {}
    for r in rows:
        by_parent.setdefault(r.get("parent_id"), []).append(r)

    def build(pid: Any) -> list[Row]:
        return [{**r, "children": build(r["id"])} for r in by_parent.get(pid, [])]

    return build(None)
