"""BOM 接口（D28）：生效 / 作废、复制为新版本、两级树。

权限：mes.bom:read（树）、mes.bom:write（复制；主表 / 明细 / 替代料走通用接口
/mes/bom、/mes/bom-line、/mes/bom-line-substitute）、mes.bom:activate（生效 / 作废）。
"""

import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

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


class SubstituteIn(BaseModel):
    """替代料（不带 bom_line_id，归属由所在行决定）。"""

    model_config = ConfigDict(extra="forbid")
    material_id: uuid.UUID | None = None
    priority: int | None = None
    remark: str | None = None


class LineIn(BaseModel):
    """明细行（不带 bom_id）；字段与 /mes/bom-line 一致，必填等规则由通用校验给出。"""

    model_config = ConfigDict(extra="forbid")
    line_no: int | None = None
    component_type: Literal["material", "product"] | None = None
    material_id: uuid.UUID | None = None
    component_product_id: uuid.UUID | None = None
    # Decimal：保留原始字符串 / 数字的小数位，供 D49 位数校验（不经 float 转换）
    qty: Decimal | None = None
    uom_id: uuid.UUID | None = None
    per_basis: str | None = None
    scrap_rate: Decimal | None = None
    consume_mode: str | None = None
    operation_id: uuid.UUID | None = None
    remark: str | None = None
    substitutes: list[SubstituteIn] = Field(default_factory=list)


class LinesIn(BaseModel):
    """整单替换草稿明细（含替代料）。"""

    model_config = ConfigDict(extra="forbid")
    lines: list[LineIn]


@router.put("/{bom_id}/lines")
def bom_replace_lines(
    session: SessionDep,
    ctx: CurrentTenant,
    bom_id: uuid.UUID,
    body: Annotated[LinesIn, Depends(perm_body("mes.bom:write", LinesIn))],
) -> Any:
    """整单替换草稿的明细与替代料（一个事务）：先查权限再校验请求体（D34）。

    非草稿 409；任一行失败整单不生效（422，loc ``["body","lines",k,...]``）。
    返回 BOM 及其 ``lines``（每行带 ``substitutes``）。
    """
    _need(ctx, "mes.bom:write")
    lines = [ln.model_dump(mode="json", exclude_unset=True) for ln in body.lines]
    return svc.replace_lines(session, ctx.id, bom_id, lines, ctx.user)
