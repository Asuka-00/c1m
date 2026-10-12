"""Work orders: lifecycle transitions and lot start / undo.

Permissions: mes.wo:release (transitions), mes.lot:start (plan/start/undo).
Plain CRUD of work orders goes through the generic /mes/work-order API.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import SessionDep
from app.core.spec.serialize import serialize
from app.mes.planning import service as svc
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/work-order", tags=["mes"])


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise HTTPException(status_code=403, detail="Not enough permissions")


class TransitionIn(BaseModel):
    action: str


class PlanIn(BaseModel):
    lot_size: int | None = Field(default=None, ge=1)
    qty: int | None = Field(default=None, ge=0)


class LotIn(BaseModel):
    qty: int = Field(ge=1)
    carrier_id: uuid.UUID | None = None
    slots: list[int] | None = None
    source_ref: str | None = Field(default=None, max_length=100)
    wafer_sources: list[str] | None = None


class StartIn(BaseModel):
    lots: list[LotIn] = Field(min_length=1, max_length=50)


class UndoIn(BaseModel):
    lot_ids: list[uuid.UUID] | None = None


@router.post("/{rid}/transition")
def wo_transition(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: TransitionIn
) -> Any:
    """release | hold | resume | complete | close | cancel."""
    _need(ctx, "mes.wo:release")
    row = svc.transition(session, ctx.id, rid, body.action, ctx.user)
    return serialize(session, ctx.id, svc.WO, [row])[0]


@router.post("/{rid}/start-plan")
def wo_start_plan(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: PlanIn
) -> Any:
    """Proposed split into lots (lot no. / wafer IDs are previews only)."""
    _need(ctx, "mes.lot:start")
    return svc.plan(session, ctx.id, rid, body.lot_size, body.qty)


@router.post("/{rid}/start")
def wo_start(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: StartIn
) -> Any:
    _need(ctx, "mes.lot:start")
    lots = svc.start(
        session, ctx.id, rid, [x.model_dump() for x in body.lots], ctx.user
    )
    return {"data": serialize(session, ctx.id, svc.LOT, lots)}


@router.post("/{rid}/undo-start")
def wo_undo_start(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: UndoIn
) -> Any:
    """Allowed only while every selected lot still waits at the first step."""
    _need(ctx, "mes.lot:start")
    return {"undone": svc.undo_start(session, ctx.id, rid, body.lot_ids, ctx.user)}
