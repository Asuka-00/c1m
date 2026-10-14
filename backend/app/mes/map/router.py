"""坐标图接口（B4）：bin 定义集与坐标图 CSV 导入（先 preview 再 commit）、按基板查询、
拆批层数量守恒校验。

权限：mes.map:import（导入）、mes.map:read（查询 / 守恒校验）。先查权限、再校验请求体（D34）；
请求体严格（§12）：未知字段（含 source / external_event_id）一律 422，手工导入 source 固定 manual。
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.deps import SessionDep
from app.core.pagination import ListParamsDep
from app.core.spec.qdates import DateTimeQ, check_range, parse_datetime
from app.mes.common.guard import MB, need, perm_body
from app.mes.common.query import one
from app.mes.map import service as svc
from app.mes.map.listing import MapListOut, list_maps
from app.platform.auth.deps import CurrentTenant

router = APIRouter(prefix="/mes/map", tags=["mes"])
IMPORT = "mes.map:import"
READ = "mes.map:read"


class ImportIn(BaseModel):
    """CSV 内容（UTF-8 文本）与可选文件名。"""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=20_000_000)
    file_name: str | None = Field(default=None, max_length=255)


class MapImportIn(ImportIn):
    """坐标图导入：可选关联批次 / 设备 / 工序（给了但不存在 422；批次不给时自动关联）。"""

    lot_id: uuid.UUID | None = None
    equipment_id: uuid.UUID | None = None
    operation_id: uuid.UUID | None = None


MAP_MAX_BYTES = 10 * MB


class SplitCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    children_qty: int = Field(ge=0)


ImportBody = Annotated[ImportIn, Depends(perm_body(IMPORT, ImportIn))]
# D39：先查权限 → 请求体超过 10MB 413 → 再解析
MapBody = Annotated[
    MapImportIn,
    Depends(perm_body(IMPORT, MapImportIn, max_bytes=MAP_MAX_BYTES)),
]


@router.post("/bin-sets/import/preview")
def bin_set_preview(session: SessionDep, ctx: CurrentTenant, body: ImportBody) -> Any:
    """Validate a bin definition CSV (set + version from its own header)."""
    return svc.bin_set_preview(session, ctx.id, body.model_dump())


@router.post("/bin-sets/import")
def bin_set_import(session: SessionDep, ctx: CurrentTenant, body: ImportBody) -> Any:
    """Import a bin definition set (422 bin_set_invalid with per-row errors)."""
    return svc.bin_set_import(session, ctx.id, body.model_dump(), ctx.user)


@router.post("/import/preview")
def map_preview(session: SessionDep, ctx: CurrentTenant, body: MapBody) -> Any:
    """Validate a substrate map CSV: per-row errors with row_no and file_line."""
    out = svc.map_preview(session, ctx.id, body.model_dump())
    return {k: v for k, v in out.items() if not k.startswith("_")}


@router.post("/import")
def map_import(session: SessionDep, ctx: CurrentTenant, body: MapBody) -> Any:
    """Import a substrate map CSV; re-importing a substrate creates a new version."""
    return svc.map_import(session, ctx.id, body.model_dump(), ctx.user)


@router.get("/maps", response_model=MapListOut)
def map_list(
    session: SessionDep,
    ctx: CurrentTenant,
    params: ListParamsDep,
    substrate_id: str | None = Query(None, max_length=100),
    lot_id: uuid.UUID | None = None,
    bin_set_id: uuid.UUID | None = None,
    substrate_type: Literal["wafer", "strip"] | None = None,
    imported_from: DateTimeQ = None,
    imported_to: DateTimeQ = None,
    latest_only: bool = False,
) -> MapListOut:
    """Imported substrate maps (no cells), paginated (page_size <= 100).

    sort_by: imported_at (default, desc), substrate_id, map_version, total_qty,
    good_qty; q searches substrate ID / file name; imported_from / imported_to is
    a half-open range [from, to) and accepts any UTC offset."""
    need(ctx, READ)
    i_from = parse_datetime("imported_from", imported_from)
    i_to = parse_datetime("imported_to", imported_to)
    check_range("imported_from", i_from, i_to)
    return list_maps(
        session,
        ctx.id,
        params,
        substrate_id=substrate_id,
        lot_id=lot_id,
        bin_set_id=bin_set_id,
        substrate_type=substrate_type,
        imported_from=i_from,
        imported_to=i_to,
        latest_only=latest_only,
    )


@router.get("/substrates/{substrate_id}")
def substrate_map(
    session: SessionDep,
    ctx: CurrentTenant,
    substrate_id: str,
    version: int | None = Query(None, ge=1),
) -> Any:
    """Map of a substrate (wafer ID): latest version by default, with cells."""
    need(ctx, READ)
    return svc.by_substrate(session, ctx.id, substrate_id, version)


@router.post("/maps/{map_id}/split-check")
def split_check(
    session: SessionDep,
    ctx: CurrentTenant,
    map_id: uuid.UUID,
    body: Annotated[SplitCheckIn, Depends(perm_body(READ, SplitCheckIn))],
) -> Any:
    """Split-level conservation: children qty + excluded qty == map total (422
    map_qty_mismatch otherwise)."""
    m = one(session, ctx.id, "substrate_map", map_id)
    if not m:
        raise HTTPException(status_code=404, detail="Record not found")
    svc.check_split(m, body.children_qty)
    return {
        "ok": True,
        "total_qty": m["total_qty"],
        "excluded_qty": m["excluded_qty"],
        "children_qty": body.children_qty,
    }
