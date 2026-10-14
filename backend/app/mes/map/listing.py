"""坐标图列表（P2，D41/D42 推迟项）。

分页 / 排序 / 筛选沿用 ``app.core.pagination``（page_size 最大 100）。只读，权限 mes.map:read。时间字段按 D45 用 UtcDateTime 输出 UTC Z。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from pydantic import BaseModel
from sqlmodel import Session

from app.core.models import UtcDateTime
from app.core.pagination import ListParams, paginate
from app.core.spec.engine import TABLES


class MapListItem(BaseModel):
    """坐标图列表项（不含坐标格；看坐标格用 GET /mes/map/substrates/{substrate_id}）。"""

    id: uuid.UUID
    substrate_id: str
    substrate_type: str
    map_version: int
    is_latest: bool
    rows: int
    cols: int
    total_qty: int
    good_qty: int | None
    excluded_qty: int | None
    bin_set_id: uuid.UUID
    bin_set_code: str | None
    bin_set_version: int | None
    lot_id: uuid.UUID | None
    lot_code: str | None
    equipment_id: uuid.UUID | None
    operation_id: uuid.UUID | None
    map_import_id: uuid.UUID
    file_name: str | None
    source: str | None
    imported_by: str | None
    imported_at: UtcDateTime | None
    created_at: UtcDateTime | None


class MapListOut(BaseModel):
    """列表响应：当前页与过滤后的总数。"""

    data: list[MapListItem]
    count: int


def list_maps(
    s: Session,
    tid: uuid.UUID,
    params: ListParams,
    *,
    substrate_id: str | None = None,
    lot_id: uuid.UUID | None = None,
    bin_set_id: uuid.UUID | None = None,
    substrate_type: str | None = None,
    imported_from: datetime | None = None,
    imported_to: datetime | None = None,
    latest_only: bool = False,
) -> MapListOut:
    """分页查询坐标图。

    筛选：基板编号精确匹配（``q`` 为基板编号 / 文件名模糊搜索）、批次、定义集、基板类型、
    导入时间区间 [from, to)、只看各基板最新版本。
    """
    m, i, b, lt = (
        TABLES["substrate_map"],
        TABLES["map_import"],
        TABLES["bin_set"],
        TABLES["lot"],
    )
    m2 = m.alias("m2")
    latest = sa.select(sa.func.max(m2.c.map_version)).where(
        m2.c.tenant_id == m.c.tenant_id, m2.c.code == m.c.code
    )
    is_latest = (m.c.map_version == latest.scalar_subquery()).label("is_latest")
    stmt = (
        sa.select(
            m.c.id,
            m.c.code.label("substrate_id"),
            m.c.substrate_type,
            m.c.map_version,
            is_latest,
            m.c.rows,
            m.c.cols,
            m.c.total_qty,
            m.c.good_qty,
            m.c.excluded_qty,
            m.c.bin_set_id,
            b.c.code.label("bin_set_code"),
            b.c.version.label("bin_set_version"),
            m.c.lot_id,
            lt.c.code.label("lot_code"),
            m.c.equipment_id,
            m.c.operation_id,
            m.c.map_import_id,
            i.c.file_name,
            i.c.source,
            i.c.imported_by,
            i.c.imported_at,
            m.c.created_at,
        )
        .select_from(
            m.join(i, i.c.id == m.c.map_import_id)
            .outerjoin(b, b.c.id == m.c.bin_set_id)
            .outerjoin(lt, lt.c.id == m.c.lot_id)
        )
        .where(m.c.tenant_id == tid)
    )
    if substrate_id:
        stmt = stmt.where(m.c.code == substrate_id.strip())
    if lot_id:
        stmt = stmt.where(m.c.lot_id == lot_id)
    if bin_set_id:
        stmt = stmt.where(m.c.bin_set_id == bin_set_id)
    if substrate_type:
        stmt = stmt.where(m.c.substrate_type == substrate_type)
    if imported_from:
        stmt = stmt.where(i.c.imported_at >= imported_from)
    if imported_to:
        stmt = stmt.where(i.c.imported_at < imported_to)
    if latest_only:
        stmt = stmt.where(m.c.map_version == latest.scalar_subquery())
    rows, count = paginate(
        s,
        stmt,
        params,
        sortable={
            "imported_at": i.c.imported_at,
            "substrate_id": m.c.code,
            "map_version": m.c.map_version,
            "total_qty": m.c.total_qty,
            "good_qty": m.c.good_qty,
        },
        default=("imported_at", "desc"),
        tiebreak=m.c.id,
        search=[m.c.code, i.c.file_name],
    )
    return MapListOut(
        data=[MapListItem.model_validate(dict(r._mapping)) for r in rows],
        count=count,
    )
