"""列表接口共享的服务端分页、排序与搜索。"""

from typing import Annotated, Any, Literal

from fastapi import Depends, Query
from sqlmodel import Session, func, or_, select

from app.core.spec.errors import query_422

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class ListParams:
    """列表查询参数（FastAPI 依赖）。

    支持 ``page``/``page_size``（默认 1/20，最大 100），
    外加 ``sort_by``（按接口白名单）、``sort_order`` 与模糊搜索 ``q``。

    Attributes:
        offset: 计算后的偏移量。
        limit: 每页条数。
        sort_by: 排序字段（未在白名单内时由 :func:`paginate` 忽略）。
        sort_order: ``asc`` / ``desc``。
        q: 搜索关键字。
    """

    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
        sort_by: str | None = None,
        sort_order: Literal["asc", "desc"] = "asc",
        q: Annotated[str | None, Query(max_length=100)] = None,
    ) -> None:
        """解析并规范化分页参数。"""
        self.limit = page_size
        self.offset = (page - 1) * page_size
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.q = (q or "").strip() or None  # 自由文本搜索，见 paginate(search=...)


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
    """对查询应用搜索、排序与分页。

    Args:
        session: 数据库会话。
        stmt: 基础查询。
        params: 列表参数。
        sortable: 允许排序的 ``{名称: 列}`` 白名单。
        default: 默认排序字段。
        tiebreak: 保证稳定排序的附加列。
        search: 参与 ``q`` 搜索的列（不区分大小写 ILIKE，OR 组合）。

    Returns:
        ``(当前页记录, 过滤后的总数)``。
    """
    if params.q and search:
        esc = params.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(or_(*(col.ilike(f"%{esc}%", escape="\\") for col in search)))
    count = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    key, order = (params.sort_by, params.sort_order) if params.sort_by else default
    if key not in sortable:
        raise query_422(
            [("sort_by", f"sort_by must be one of: {', '.join(sorted(sortable))}")]
        )
    column = sortable[key]
    stmt = stmt.order_by(
        column.desc().nulls_last() if order == "desc" else column.asc().nulls_last(),
        tiebreak,
    )
    rows = session.exec(stmt.offset(params.offset).limit(params.limit)).all()
    return list(rows), count
