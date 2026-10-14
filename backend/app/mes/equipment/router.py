"""设备接口：状态看板、E10 手动改状态、PM 状态与完成登记。

权限：mes.equipment:read（看板 / PM 状态）、mes.equipment:e10（手动改 E10）、
mes.equipment:pm（登记 PM 完成）、mes.equipment:qual（登记 PM 后 Qual 结果）。E10 履历、PM 计划、停机记录的 CRUD 走通用接口。
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.deps import SessionDep
from app.core.spec.errors import err_422
from app.mes.common import idempotency as idem
from app.mes.common.guard import perm_body
from app.mes.common.query import one
from app.mes.equipment import mount as mount_svc
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
    session: SessionDep,
    ctx: CurrentTenant,
    eq_id: uuid.UUID,
    body: E10In,
    idempotency_key: Annotated[str | None, Header(alias=idem.HEADER)] = None,
) -> Any:
    """Change the equipment E10 state manually (transition table enforced).
    Idempotency-Key (D57): same key + same body replays the first response; same
    key + different body 422 idempotency_key_reused."""
    _need(ctx, "mes.equipment:e10")
    data = body.model_dump()
    return idem.run(
        session,
        ctx.id,
        ctx.user,
        "POST /mes/eqp/{eq_id}/e10",
        idempotency_key,
        {"eq_id": eq_id, **data},
        lambda: svc.e10_change(session, ctx.id, eq_id, data, ctx.user),
    )


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


class MountIn(BaseModel):
    # P1 严格载荷（bom.md §12）：未知字段 / source（人工接口固定为 manual）一律 422
    model_config = ConfigDict(extra="forbid")

    port_code: str = Field(min_length=1, max_length=64)
    material_lot_id: uuid.UUID | None = None
    material_lot_code: str | None = Field(default=None, max_length=64)
    mounted_at: datetime | None = None
    external_event_id: str | None = Field(default=None, max_length=128)
    comment: str | None = Field(default=None, max_length=300)


class QualResultIn(BaseModel):
    # 只接受可写字段：传了只读字段（qual_status、done_by …）即 422
    model_config = ConfigDict(extra="forbid")

    result: Literal["pass", "fail"]
    comment: str | None = Field(default=None, max_length=300)


@router.post("/qual/{task_id}/result")
def qual_result(
    session: SessionDep,
    ctx: CurrentTenant,
    task_id: uuid.UUID,
    body: Annotated[
        QualResultIn, Depends(perm_body("mes.equipment:qual", QualResultIn))
    ],
) -> Any:
    """Record a Qual result after PM: pass → equipment ready; fail → stays WAIT_QUAL
    with a retest task (409 qual_task_closed when the task is already recorded)."""
    _need(ctx, "mes.equipment:qual")
    return svc.record_result(session, ctx.id, task_id, body.model_dump(), ctx.user)


class UnmountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unmounted_at: datetime | None = None


@router.get("/mount/at")
def mount_at(
    session: SessionDep,
    ctx: CurrentTenant,
    eq_id: uuid.UUID,
    at: datetime,
    port_code: str | None = Query(None, max_length=64),
) -> Any:
    """Material lots mounted on an equipment at a point in time (traceability)."""
    _need(ctx, "mes.equipment:read")
    if at.tzinfo is None:
        raise err_422(["query", "at"], "at: timezone required", "timezone_required")
    return {"data": mount_svc.mounted_at(session, ctx.id, eq_id, at, port_code)}


@router.post("/mount/{mount_id}/unmount")
def unmount(
    session: SessionDep,
    ctx: CurrentTenant,
    mount_id: uuid.UUID,
    body: Annotated[
        UnmountIn | None,
        Depends(perm_body("mes.equipment:mount", UnmountIn, optional=True)),
    ],
) -> Any:
    """Unmount a material lot (unmounted_at defaults to now)."""
    _need(ctx, "mes.equipment:mount")
    data = body.model_dump() if body else {}
    return {"data": mount_svc.unmount(session, ctx.id, mount_id, data, ctx.user)}


@router.post("/{eq_id}/mount")
def mount(
    session: SessionDep,
    ctx: CurrentTenant,
    eq_id: uuid.UUID,
    body: Annotated[MountIn, Depends(perm_body("mes.equipment:mount", MountIn))],
) -> Any:
    """Manual mount (409 port_occupied when the port already holds a lot)."""
    _need(ctx, "mes.equipment:mount")
    return mount_svc.mount(
        session, ctx.id, eq_id, body.model_dump(), ctx.user, source="manual"
    )
