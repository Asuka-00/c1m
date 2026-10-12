"""Shared server-side pagination + sorting for list endpoints."""

from typing import Annotated, Any, Literal

from fastapi import Depends, HTTPException, Query
from sqlmodel import Session, func, or_, select

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class ListParams:
    """`page`/`page_size` (default 1/20, max 100) — or legacy `skip`/`limit` —
    plus `sort_by` (whitelisted per endpoint) and `sort_order`."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
        skip: Annotated[int | None, Query(ge=0)] = None,
        limit: Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)] = None,
        sort_by: str | None = None,
        sort_order: Literal["asc", "desc"] = "asc",
        q: Annotated[str | None, Query(max_length=100)] = None,
    ) -> None:
        self.limit = limit or page_size
        self.offset = skip if skip is not None else (page - 1) * page_size
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.q = (q or "").strip() or None  # free-text search, see paginate(search=...)


ListParamsDep = Annotated[ListParams, Depends()]


def paginate(
    session: Session,
    stmt: Any,
    params: ListParams,
    sortable: dict[str, Any],
    default: tuple[str, Literal["asc", "desc"]],
    tiebreak: Any,
    search: list[Any] | None = None,
) -> tuple[list[Any], int]:
    """Apply `q` search (case-insensitive ILIKE OR-ed across the `search` columns),
    sorting (only whitelisted columns) + offset/limit; return (rows, filtered total).
    Runs on the caller's statement, so tenant filters / RLS still apply."""
    if params.q and search:
        esc = params.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(or_(*(col.ilike(f"%{esc}%", escape="\\") for col in search)))
    count = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    key, order = (params.sort_by, params.sort_order) if params.sort_by else default
    if key not in sortable:
        raise HTTPException(
            status_code=422,
            detail=f"sort_by must be one of: {', '.join(sorted(sortable))}",
        )
    column = sortable[key]
    stmt = stmt.order_by(
        column.desc().nulls_last() if order == "desc" else column.asc().nulls_last(),
        tiebreak,
    )
    rows = session.exec(stmt.offset(params.offset).limit(params.limit)).all()
    return list(rows), count
