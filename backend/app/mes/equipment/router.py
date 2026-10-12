"""设备接口：状态看板、E10 手动改状态、PM 状态与完成登记。

权限：mes.equipment:read（看板 / PM 状态）、mes.equipment:e10（手动改 E10）、
mes.equipment:pm（登记 PM 完成）。E10 履历、PM 计划、停机记录的 CRUD 走通用接口。
"""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import SessionDep
from app.mes.common.query import one
from app.mes.equipment import service as svc
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/eqp", tags=["mes"])


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise HTTPException(status_code=403, detail="Not enough permissions")


@router.get("/board")
def board(session: SessionDep, ctx: CurrentTenant) -> Any:
    """Equipment status board (E10 state, allowed transitions, PM, downtime)."""
    _need(ctx, "mes.equipment:read")
    return {"data": svc.equipment_board(session, ctx.id)}


class E10In(BaseModel):
    to_state_id: uuid.UUID
    reason_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=300)


@router.post("/{eq_id}/e10")
def change_e10(
    session: SessionDep, ctx: CurrentTenant, eq_id: uuid.UUID, body: E10In
) -> Any:
    """Change the equipment E10 state manually (transition table enforced)."""
    _need(ctx, "mes.equipment:e10")
    return svc.e10_change(session, ctx.id, eq_id, body.model_dump(), ctx.user)


@router.get("/{eq_id}/pm")
def pm(session: SessionDep, ctx: CurrentTenant, eq_id: uuid.UUID) -> Any:
    """PM due status of one equipment."""
    _need(ctx, "mes.equipment:read")
    eq = one(session, ctx.id, "equipment", eq_id)
    if not eq:
        raise HTTPException(status_code=404, detail="equipment not found")
    return {"data": svc.pm_status(session, ctx.id, eq)}


class PmIn(BaseModel):
    equipment_id: uuid.UUID
    result: Literal["ok", "ng"] = "ok"
    comment: str | None = Field(default=None, max_length=300)


@router.post("/pm/{plan_id}/complete")
def pm_done(
    session: SessionDep, ctx: CurrentTenant, plan_id: uuid.UUID, body: PmIn
) -> Any:
    """Record a PM completion (resets the plan's day / lot interval)."""
    _need(ctx, "mes.equipment:pm")
    return svc.pm_complete(session, ctx.id, plan_id, body.model_dump(), ctx.user)
