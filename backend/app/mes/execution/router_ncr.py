"""NCR / MRB 接口：登记、提案、审批、取消。

权限：mes.ncr:read（详情）、mes.ncr:write（登记 / 提案 / 取消）、mes.ncr:approve（审批）。
"""

import uuid
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core import error_codes as ec
from app.core.deps import SessionDep
from app.core.spec.errors import coded
from app.mes.execution.ncr import flow
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/exec/ncr", tags=["mes"])


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise coded(403, ec.PERMISSION_DENIED, "Not enough permissions")


class NcrIn(BaseModel):
    lot_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    severity: Literal["minor", "major", "critical"] = "major"
    defect_code_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=4000)
    unit_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)
    qty: int | None = Field(default=None, ge=1)
    hold: bool = True
    reason_id: uuid.UUID | None = None


class ProposeIn(BaseModel):
    disposition: Literal["release", "use_as_is", "rework", "scrap", "downgrade", "rtv"]
    comment: str | None = Field(default=None, max_length=300)
    scrap_reason_id: uuid.UUID | None = None


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=300)


class CancelIn(BaseModel):
    comment: str | None = Field(default=None, max_length=300)


@router.post("")
def ncr_create(session: SessionDep, ctx: CurrentTenant, body: NcrIn) -> Any:
    """Raise an NCR on a lot (holds the lot unless hold=false)."""
    _need(ctx, "mes.ncr:write")
    return flow.create(session, ctx.id, body.model_dump(), ctx.user)


@router.get("/{ncr_id}")
def ncr_detail(session: SessionDep, ctx: CurrentTenant, ncr_id: uuid.UUID) -> Any:
    _need(ctx, "mes.ncr:read")
    return flow.detail(session, ctx.id, ncr_id)


@router.post("/{ncr_id}/propose")
def ncr_propose(
    session: SessionDep, ctx: CurrentTenant, ncr_id: uuid.UUID, body: ProposeIn
) -> Any:
    """Propose a disposition; starts a new approval round."""
    _need(ctx, "mes.ncr:write")
    return flow.propose(session, ctx.id, ncr_id, body.model_dump(), ctx.user)


@router.post("/{ncr_id}/approve")
def ncr_approve(
    session: SessionDep, ctx: CurrentTenant, ncr_id: uuid.UUID, body: DecisionIn
) -> Any:
    """Approve or reject one level; the last approval executes the disposition."""
    _need(ctx, "mes.ncr:approve")
    return flow.approve(session, ctx.id, ncr_id, body.model_dump(), ctx.user)


@router.post("/{ncr_id}/cancel")
def ncr_cancel(
    session: SessionDep, ctx: CurrentTenant, ncr_id: uuid.UUID, body: CancelIn
) -> Any:
    """Cancel an open NCR and release its hold."""
    _need(ctx, "mes.ncr:write")
    return flow.cancel(session, ctx.id, ncr_id, body.model_dump(), ctx.user)
