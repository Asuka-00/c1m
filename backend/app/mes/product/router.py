"""BOM 接口（D28）：生效 / 作废、复制为新版本、两级树。

权限：mes.bom:read（树）、mes.bom:write（复制；主表 / 明细 / 替代料走通用接口
/mes/bom、/mes/bom-line、/mes/bom-line-substitute）、mes.bom:activate（生效 / 作废）。
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.core.deps import SessionDep
from app.core.spec.engine import ENTITIES
from app.core.spec.serialize import serialize
from app.mes.common.guard import perm_body
from app.mes.product import bom as svc
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/bom", tags=["mes"])


class NoBody(BaseModel):
    """动作接口不接受任何字段：不带请求体或 ``{}`` 放行，带任何字段 422（D4 / D32）。"""

    model_config = ConfigDict(extra="forbid")


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise HTTPException(status_code=403, detail="Not enough permissions")


@router.get("/tree")
def bom_tree(
    session: SessionDep,
    ctx: CurrentTenant,
    product_id: uuid.UUID | None = None,
    bom_id: uuid.UUID | None = None,
) -> Any:
    """Two-level BOM tree: a given version, or the product's active version."""
    _need(ctx, "mes.bom:read")
    return svc.tree(session, ctx.id, product_id, bom_id)


@router.post("/{bom_id}/activate")
def bom_activate(
    session: SessionDep,
    ctx: CurrentTenant,
    bom_id: uuid.UUID,
    _body: Annotated[
        NoBody | None, Depends(perm_body("mes.bom:activate", NoBody, optional=True))
    ],
) -> Any:
    """Draft → active; the previous active version becomes superseded.

    Any request body (e.g. confirmed_by / confirmed_at) is ignored: the confirmer is
    always the current user and the time is now.
    """
    _need(ctx, "mes.bom:activate")
    row = svc.activate(session, ctx.id, bom_id, ctx.user)
    return serialize(session, ctx.id, ENTITIES["bom"], [row])[0]


@router.post("/{bom_id}/void")
def bom_void(
    session: SessionDep,
    ctx: CurrentTenant,
    bom_id: uuid.UUID,
    _body: Annotated[
        NoBody | None, Depends(perm_body("mes.bom:activate", NoBody, optional=True))
    ],
) -> Any:
    """Draft / active → void (lots that locked it keep the reference)."""
    _need(ctx, "mes.bom:activate")
    row = svc.void(session, ctx.id, bom_id, ctx.user)
    return serialize(session, ctx.id, ENTITIES["bom"], [row])[0]


@router.post("/{bom_id}/copy")
def bom_copy(
    session: SessionDep,
    ctx: CurrentTenant,
    bom_id: uuid.UUID,
    _body: Annotated[
        NoBody | None, Depends(perm_body("mes.bom:write", NoBody, optional=True))
    ],
) -> Any:
    """Copy any version (lines + substitutes) to the next draft version."""
    _need(ctx, "mes.bom:write")
    row = svc.copy(session, ctx.id, bom_id, ctx.user)
    return serialize(session, ctx.id, ENTITIES["bom"], [row])[0]
