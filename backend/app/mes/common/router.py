"""MES 主数据通用接口：为每个规格实体提供 ``/mes/{entity}[...]``。

权限：当前租户（X-Tenant-ID）内的 ``mes.<module>:read`` / ``mes.<module>:write``。
租户隔离：tenant_id 过滤 + Postgres RLS。
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.core import error_codes as ec
from app.core.deps import SessionDep
from app.core.pagination import ListParamsDep
from app.core.spec.base import get_entity
from app.core.spec.engine import ENTITIES, EXTRA_PERMISSIONS, MODULES, Entity, perm
from app.core.spec.errors import coded
from app.core.spec.excel import export_xlsx, import_xlsx, template_path
from app.core.spec.query import distinct_values, get_row, list_rows, tree
from app.core.spec.serialize import serialize
from app.core.spec.validate import attr_defs, attr_options
from app.core.spec.write import (
    create_row,
    delete_row,
    new_version,
    set_status,
    update_row,
)
from app.mes.common import coderule
from app.mes.common.meta import all_meta
from app.mes.common.uom import convert
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes", tags=["mes"])
RESERVED = {"page", "page_size", "skip", "limit", "sort_by", "sort_order", "q"}


def require_entity(
    ctx: TenantContext, code: str, action: Literal["read", "write"]
) -> Entity:
    """获取实体并校验当前租户上下文是否具备其模块权限。

    Raises:
        HTTPException: 实体不存在（404）或无权限（403）。
    """
    e = get_entity(code)
    if not ctx.can(perm(e.pmod, action)):
        raise coded(403, ec.PERMISSION_DENIED, "Not enough permissions")
    return e


def _one(
    session: SessionDep, ctx: TenantContext, e: Entity, row: dict[str, Any]
) -> dict[str, Any]:
    return serialize(session, ctx.id, e, [row])[0]


@router.get("/_meta")
def mes_meta(ctx: CurrentTenant) -> Any:
    """Entity metadata (fields, enums, refs, flags) the frontend renders from;
    each entity carries `can_read` / `can_write` for the current user."""
    meta = all_meta()
    codes = [*EXTRA_PERMISSIONS] + [
        perm(m, a) for m in MODULES for a in ("read", "write")
    ]
    meta["perms"] = [p for p in codes if ctx.can(p)]
    for m in meta["entities"]:
        m["can_read"] = ctx.can(m["read"])
        m["can_write"] = ctx.can(m["write"])
    return meta


@router.get("/_attrs/{entity}")
def mes_attr_defs(session: SessionDep, ctx: CurrentTenant, entity: str) -> Any:
    """Custom attribute definitions of an entity type (with resolved options)."""
    e = require_entity(ctx, entity, "read")
    return [
        {
            "code": d["code"],
            "name": d["name"],
            "data_type": d["data_type"],
            "required": bool(d["required"]),
            "options": attr_options(session, ctx.id, d),
        }
        for d in attr_defs(session, ctx.id, e)
    ]


class CodeGenIn(BaseModel):
    count: int = Field(default=1, ge=1, le=100)
    context: dict[str, Any] = Field(default_factory=dict)


@router.post("/code-rule/{rid}/preview")
def code_rule_preview(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: CodeGenIn
) -> Any:
    """Next codes without reserving them."""
    e = require_entity(ctx, "code_rule", "read")
    rule = get_row(session, e, ctx.id, rid)
    return {"codes": coderule.preview(session, ctx.id, rule, body.count, body.context)}


@router.post("/code-rule/{rid}/generate")
def code_rule_generate(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: CodeGenIn
) -> Any:
    """Reserve codes (atomically increments the rule's counter)."""
    e = require_entity(ctx, "code_rule", "write")
    rule = get_row(session, e, ctx.id, rid)
    return {"codes": coderule.generate(session, ctx.id, rule, body.count, body.context)}


@router.get("/_convert")
def uom_convert(
    session: SessionDep,
    ctx: CurrentTenant,
    from_uom: uuid.UUID,
    to_uom: uuid.UUID,
    value: float = 1.0,
) -> Any:
    """Convert `value` between units (direct, inverse or multi-hop conversions)."""
    require_entity(ctx, "uom", "read")
    return convert(session, ctx.id, from_uom, to_uom, value)


@router.get("/{entity}")
def mes_list(
    session: SessionDep,
    ctx: CurrentTenant,
    entity: str,
    params: ListParamsDep,
    request: Request,
) -> Any:
    """Paginated list (20/page default) with ?q= search, ?sort_by=, and filters
    on any enum/bool/ref field (`?site_id=<uuid>`, `?status=active`, ...)."""
    e = require_entity(ctx, entity, "read")
    filters = {
        k: v for k, v in request.query_params.items() if k not in RESERVED and v != ""
    }
    rows, count = list_rows(
        session,
        e,
        ctx.id,
        q=params.q,
        filters=filters,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
        offset=params.offset,
        limit=params.limit,
    )
    return {"data": serialize(session, ctx.id, e, rows), "count": count}


@router.get("/{entity}/distinct/{field}")
def mes_distinct(
    session: SessionDep,
    ctx: CurrentTenant,
    entity: str,
    field: str,
    q: str | None = None,
) -> Any:
    """Distinct values of a text filter field (dropdown filter options)."""
    e = require_entity(ctx, entity, "read")
    return {"data": distinct_values(session, e, ctx.id, field, q)}


@router.get("/{entity}/tree")
def mes_tree(session: SessionDep, ctx: CurrentTenant, entity: str) -> Any:
    e = require_entity(ctx, entity, "read")
    return tree(session, ctx.id, e)


@router.get("/{entity}/export")
def mes_export(
    session: SessionDep,
    ctx: CurrentTenant,
    entity: str,
    request: Request,
    q: str | None = None,
) -> Response:
    """Export as xlsx, honouring the same ?q= and filters as the list."""
    e = require_entity(ctx, entity, "read")
    filters = {
        k: v for k, v in request.query_params.items() if k not in RESERVED and v != ""
    }
    return Response(
        export_xlsx(session, ctx.id, e, q=q, filters=filters),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{e.code}.xlsx"'},
    )


@router.get("/{entity}/import-template")
def mes_import_template(ctx: CurrentTenant, entity: str) -> FileResponse:
    """Blank import template (.xlsx, header row + README sheet) stored with the source."""
    e = require_entity(ctx, entity, "write")
    if e.readonly:
        raise coded(405, ec.READ_ONLY_ENTITY, "Read-only entity")
    return FileResponse(
        template_path(e),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{e.code}-template.xlsx",
    )


@router.post("/{entity}/import")
async def mes_import(
    session: SessionDep,
    ctx: CurrentTenant,
    entity: str,
    file: Annotated[UploadFile, File()],
) -> Any:
    """Upsert rows from an .xlsx (same columns as the export); all-or-nothing."""
    e = require_entity(ctx, entity, "write")
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise coded(413, ec.FILE_TOO_LARGE, "File too large")
    return import_xlsx(session, ctx.id, e, data, ctx.user)


@router.get("/{entity}/{rid}")
def mes_get(
    session: SessionDep, ctx: CurrentTenant, entity: str, rid: uuid.UUID
) -> Any:
    e = require_entity(ctx, entity, "read")
    return _one(session, ctx, e, get_row(session, e, ctx.id, rid))


@router.post("/{entity}")
def mes_create(
    session: SessionDep, ctx: CurrentTenant, entity: str, body: dict[str, Any]
) -> Any:
    e = require_entity(ctx, entity, "write")
    return _one(session, ctx, e, create_row(session, ctx.id, e, body, ctx.user))


@router.patch("/{entity}/{rid}")
def mes_update(
    session: SessionDep,
    ctx: CurrentTenant,
    entity: str,
    rid: uuid.UUID,
    body: dict[str, Any],
) -> Any:
    e = require_entity(ctx, entity, "write")
    return _one(session, ctx, e, update_row(session, ctx.id, e, rid, body, ctx.user))


@router.delete("/{entity}/{rid}")
def mes_delete(
    session: SessionDep, ctx: CurrentTenant, entity: str, rid: uuid.UUID
) -> Any:
    e = require_entity(ctx, entity, "write")
    delete_row(session, ctx.id, e, rid, ctx.user)
    return {"message": "Deleted"}


class StatusIn(BaseModel):
    status: str


@router.post("/{entity}/{rid}/status")
def mes_status(
    session: SessionDep, ctx: CurrentTenant, entity: str, rid: uuid.UUID, body: StatusIn
) -> Any:
    """Versioned data: draft -> active -> inactive (-> active); activating a
    version deactivates the other active version of the same code."""
    e = require_entity(ctx, entity, "write")
    return _one(
        session, ctx, e, set_status(session, ctx.id, e, rid, body.status, ctx.user)
    )


@router.post("/{entity}/{rid}/new-version")
def mes_new_version(
    session: SessionDep, ctx: CurrentTenant, entity: str, rid: uuid.UUID
) -> Any:
    """Copy a version (incl. child rows such as route steps) as a new draft."""
    e = require_entity(ctx, entity, "write")
    return _one(session, ctx, e, new_version(session, ctx.id, e, rid, ctx.user))


__all__ = ["router", "ENTITIES", "Query"]
