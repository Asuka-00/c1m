"""Generic MES master-data API: /mes/{entity}[...] for every spec in app.mes.

Permissions: mes.<module>:read / mes.<module>:write in the current tenant
(X-Tenant-ID). Tenant isolation: tenant_id filter + Postgres RLS.
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import CurrentTenant, SessionDep
from app.api.pagination import ListParamsDep
from app.mes import coderule
from app.mes.core import ENTITIES, Entity, perm
from app.mes.excel import export_xlsx, import_xlsx
from app.mes.meta import all_meta
from app.mes.service import (
    attr_defs,
    attr_options,
    create_row,
    delete_row,
    get_entity,
    get_row,
    list_rows,
    new_version,
    serialize,
    set_status,
    tree,
    update_row,
)
from app.mes.uom import convert
from app.tenancy import TenantContext

router = APIRouter(prefix="/mes", tags=["mes"])
RESERVED = {"page", "page_size", "skip", "limit", "sort_by", "sort_order", "q"}


def _ent(ctx: TenantContext, code: str, action: Literal["read", "write"]) -> Entity:
    e = get_entity(code)
    if not ctx.can(perm(e.module, action)):
        raise HTTPException(status_code=403, detail="Not enough permissions")
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
    for m in meta["entities"]:
        m["can_read"] = ctx.can(m["read"])
        m["can_write"] = ctx.can(m["write"])
    return meta


@router.get("/_attrs/{entity}")
def mes_attr_defs(session: SessionDep, ctx: CurrentTenant, entity: str) -> Any:
    """Custom attribute definitions of an entity type (with resolved options)."""
    e = _ent(ctx, entity, "read")
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
    e = _ent(ctx, "code_rule", "read")
    rule = get_row(session, e, ctx.id, rid)
    return {"codes": coderule.preview(session, ctx.id, rule, body.count, body.context)}


@router.post("/code-rule/{rid}/generate")
def code_rule_generate(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: CodeGenIn
) -> Any:
    """Reserve codes (atomically increments the rule's counter)."""
    e = _ent(ctx, "code_rule", "write")
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
    _ent(ctx, "uom", "read")
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
    e = _ent(ctx, entity, "read")
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


@router.get("/{entity}/tree")
def mes_tree(session: SessionDep, ctx: CurrentTenant, entity: str) -> Any:
    e = _ent(ctx, entity, "read")
    return tree(session, ctx.id, e)


@router.get("/{entity}/export")
def mes_export(session: SessionDep, ctx: CurrentTenant, entity: str) -> Response:
    e = _ent(ctx, entity, "read")
    return Response(
        export_xlsx(session, ctx.id, e),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{e.code}.xlsx"'},
    )


@router.post("/{entity}/import")
async def mes_import(
    session: SessionDep,
    ctx: CurrentTenant,
    entity: str,
    file: Annotated[UploadFile, File()],
) -> Any:
    """Upsert rows from an .xlsx (same columns as the export); all-or-nothing."""
    e = _ent(ctx, entity, "write")
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")
    return import_xlsx(session, ctx.id, e, data, ctx.user)


@router.get("/{entity}/{rid}")
def mes_get(
    session: SessionDep, ctx: CurrentTenant, entity: str, rid: uuid.UUID
) -> Any:
    e = _ent(ctx, entity, "read")
    return _one(session, ctx, e, get_row(session, e, ctx.id, rid))


@router.post("/{entity}")
def mes_create(
    session: SessionDep, ctx: CurrentTenant, entity: str, body: dict[str, Any]
) -> Any:
    e = _ent(ctx, entity, "write")
    return _one(session, ctx, e, create_row(session, ctx.id, e, body, ctx.user))


@router.patch("/{entity}/{rid}")
def mes_update(
    session: SessionDep,
    ctx: CurrentTenant,
    entity: str,
    rid: uuid.UUID,
    body: dict[str, Any],
) -> Any:
    e = _ent(ctx, entity, "write")
    return _one(session, ctx, e, update_row(session, ctx.id, e, rid, body, ctx.user))


@router.delete("/{entity}/{rid}")
def mes_delete(
    session: SessionDep, ctx: CurrentTenant, entity: str, rid: uuid.UUID
) -> Any:
    e = _ent(ctx, entity, "write")
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
    e = _ent(ctx, entity, "write")
    return _one(
        session, ctx, e, set_status(session, ctx.id, e, rid, body.status, ctx.user)
    )


@router.post("/{entity}/{rid}/new-version")
def mes_new_version(
    session: SessionDep, ctx: CurrentTenant, entity: str, rid: uuid.UUID
) -> Any:
    """Copy a version (incl. child rows such as route steps) as a new draft."""
    e = _ent(ctx, entity, "write")
    return _one(session, ctx, e, new_version(session, ctx.id, e, rid, ctx.user))


__all__ = ["router", "ENTITIES", "Query"]
