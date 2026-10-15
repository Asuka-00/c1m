"""工具 / 耗材寿命接口（P2-B10）：装卸、更换、计数上报 / 调整、重置、履历。

权限：mes.equipment:tool_mount（装 / 卸 / 换）、mes.equipment:tool_count（上报 / 调整 / 重置）、
mes.equipment:read（履历）。人工接口不接受 ``source``（D30，固定 manual）；
外部事件号按 (source, external_event_id) 幂等，重复返回 200 + duplicate=true。
小数一律十进制字符串（D50），时间 UTC Z（D45）。
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.deps import SessionDep
from app.mes.common.guard import perm_body
from app.mes.equipment import tools as svc
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/eqp/tools", tags=["mes"])
MOUNT = "mes.equipment:tool_mount"
COUNT = "mes.equipment:tool_count"
Reason = Literal["life_end", "broken", "pm", "swap", "other"]


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise HTTPException(status_code=403, detail="Not enough permissions")


def six(v: Decimal) -> Decimal:
    """numeric(18,6)：最多 6 位小数（``too_many_decimals``）。"""
    if not v.is_finite():
        raise ValueError("must be a finite number")
    if v.as_tuple().exponent < -6:  # type: ignore[operator]
        raise ValueError("too_many_decimals (max 6)")
    if abs(v) >= Decimal(10) ** 12:
        raise ValueError("out of range")
    return v


class UsageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta: Decimal
    equipment_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    occurred_at: datetime | None = None
    reason_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=300)
    external_event_id: str | None = Field(default=None, max_length=128)

    _six = field_validator("delta")(six)


class MountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: uuid.UUID
    sub_unit_id: uuid.UUID | None = None
    port_code: str | None = Field(default=None, max_length=64)
    mounted_at: datetime | None = None
    comment: str | None = Field(default=None, max_length=300)


class UnmountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason
    unmounted_at: datetime | None = None
    comment: str | None = Field(default=None, max_length=300)


class ReplaceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_tool_id: uuid.UUID
    reason: Reason
    comment: str | None = Field(default=None, max_length=300)


class ResetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=300)


@router.post("/{tool_id}/usage")
def usage(
    session: SessionDep,
    ctx: CurrentTenant,
    tool_id: uuid.UUID,
    body: Annotated[UsageIn, Depends(perm_body(COUNT, UsageIn))],
) -> Any:
    """Report tool usage (delta > 0) or adjust (delta < 0, reason_id required)."""
    _need(ctx, COUNT)
    return svc.report_usage(session, ctx.id, tool_id, body.model_dump(), ctx.user)


@router.post("/{tool_id}/reset")
def reset(
    session: SessionDep,
    ctx: CurrentTenant,
    tool_id: uuid.UUID,
    body: Annotated[ResetIn, Depends(perm_body(COUNT, ResetIn))],
) -> Any:
    """Reset the usage count after refurbish (pending_maintenance -> available)."""
    _need(ctx, COUNT)
    return svc.reset(session, ctx.id, tool_id, body.model_dump(), ctx.user)


@router.post("/{tool_id}/mount")
def mount(
    session: SessionDep,
    ctx: CurrentTenant,
    tool_id: uuid.UUID,
    body: Annotated[MountIn, Depends(perm_body(MOUNT, MountIn))],
) -> Any:
    """Mount a tool on an equipment (409 tool_already_mounted / tool_not_usable)."""
    _need(ctx, MOUNT)
    return svc.mount(session, ctx.id, tool_id, body.model_dump(), ctx.user)


@router.post("/{tool_id}/unmount")
def unmount(
    session: SessionDep,
    ctx: CurrentTenant,
    tool_id: uuid.UUID,
    body: Annotated[UnmountIn, Depends(perm_body(MOUNT, UnmountIn))],
) -> Any:
    """Unmount a tool (409 tool_not_mounted)."""
    _need(ctx, MOUNT)
    return svc.unmount(session, ctx.id, tool_id, body.model_dump(), ctx.user)


@router.post("/{tool_id}/replace")
def replace(
    session: SessionDep,
    ctx: CurrentTenant,
    tool_id: uuid.UUID,
    body: Annotated[ReplaceIn, Depends(perm_body(MOUNT, ReplaceIn))],
) -> Any:
    """Replace a mounted tool with another of the same type in one transaction."""
    _need(ctx, MOUNT)
    return svc.replace(session, ctx.id, tool_id, body.model_dump(), ctx.user)


@router.get("/{tool_id}/usage")
def usage_history(
    session: SessionDep,
    ctx: CurrentTenant,
    tool_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Any:
    """Usage history of a tool, newest first."""
    _need(ctx, "mes.equipment:read")
    off = (page - 1) * page_size
    return svc.history(session, ctx.id, "tool_usage", tool_id, off, page_size)


@router.get("/{tool_id}/mounts")
def mount_history(
    session: SessionDep,
    ctx: CurrentTenant,
    tool_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Any:
    """Mount / unmount history of a tool, newest first."""
    _need(ctx, "mes.equipment:read")
    off = (page - 1) * page_size
    return svc.history(session, ctx.id, "tool_mount_log", tool_id, off, page_size)
