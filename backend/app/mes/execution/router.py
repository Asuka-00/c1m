"""批次执行接口：阶段作业、检查预览、Hold、拆合批。

权限：mes.exec:read（上下文 / 预览）、mes.exec:write（阶段作业）、mes.exec:override
（强制放行阻断检查，须填原因）、mes.exec:hold（手工 Hold / 释放）、mes.exec:split / mes.exec:merge、
mes.exec:jump（跳站）、mes.exec:adjust（在制报废 / 补数）。
阶段被阻断时返回 409 ``{"detail": {"code": "check_blocked", "results": [...]}}``。
"""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import SessionDep
from app.core.spec.engine import ENTITIES
from app.core.spec.serialize import serialize
from app.mes.common.query import one
from app.mes.execution import dispatch
from app.mes.execution import service as sm
from app.mes.execution import service as svc
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/exec", tags=["mes"])
Stage = Literal["move_in", "track_in", "track_out", "move_out"]


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise HTTPException(status_code=403, detail="Not enough permissions")


class DcIn(BaseModel):
    measurement_item_id: uuid.UUID
    unit_id: uuid.UUID | None = None
    site_no: int = Field(default=1, ge=1)
    value: float | None = None


class ScrapIn(BaseModel):
    reason_id: uuid.UUID
    unit_id: uuid.UUID | None = None
    qty: int | None = Field(default=None, ge=1)


class ReworkUnitIn(BaseModel):
    reason_id: uuid.UUID
    unit_id: uuid.UUID


class StageIn(BaseModel):
    equipment_id: uuid.UUID | None = None
    recipe_id: uuid.UUID | None = None
    eqp_recipe: str | None = Field(default=None, max_length=200)
    reticle_id: uuid.UUID | None = None
    carrier_id: uuid.UUID | None = None
    tool_ids: list[uuid.UUID] | None = None
    material_lot_ids: list[uuid.UUID] | None = None
    dc: list[DcIn] | None = None
    scrap: list[ScrapIn] | None = None
    rework_units: list[ReworkUnitIn] | None = None
    branch: bool = False
    rework: bool = False
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)


class HoldIn(BaseModel):
    reason_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=300)


class ReleaseIn(BaseModel):
    reason_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=300)


@router.get("/lots/{lot_id}")
def lot_context(session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID) -> Any:
    _need(ctx, "mes.exec:read")
    out = svc.context(session, ctx.id, lot_id)
    lot = one(session, ctx.id, "lot", lot_id)
    if lot:
        out["sm"] = sm.sm_context(session, ctx.id, lot)
    return out


@router.post("/lots/{lot_id}/preview/{stage}")
def lot_preview(
    session: SessionDep,
    ctx: CurrentTenant,
    lot_id: uuid.UUID,
    stage: Stage,
    body: StageIn,
) -> Any:
    """Evaluate the bound checks for a stage without executing it (logged as preview)."""
    _need(ctx, "mes.exec:read")
    return {
        "results": svc.preview(
            session, ctx.id, lot_id, stage, body.model_dump(), ctx.user
        )
    }


@router.post("/lots/{lot_id}/hold")
def lot_hold(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: HoldIn
) -> Any:
    _need(ctx, "mes.exec:hold")
    lot = svc.manual_hold(
        session, ctx.id, lot_id, body.reason_id, body.comment, ctx.user
    )
    return serialize(
        session,
        ctx.id,
        ENTITIES["lot"],
        [one(session, ctx.id, "lot", lot["id"]) or lot],
    )[0]


@router.get("/holds")
def holds_list(
    session: SessionDep,
    ctx: CurrentTenant,
    status: Literal["active", "released", "all"] = "active",
    reason_id: uuid.UUID | None = None,
    source: str | None = None,
    product_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Any:
    """Holds for the Hold management page (active by default; history / all)."""
    _need(ctx, "mes.exec:read")
    return {
        "data": svc.list_holds(
            session,
            ctx.id,
            {"active": True, "released": False}.get(status),
            reason_id,
            source,
            product_id,
            date_from,
            date_to,
        )
    }


class BatchReleaseIn(BaseModel):
    hold_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    reason_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=300)


@router.post("/holds/release-batch")
def holds_release_batch(
    session: SessionDep, ctx: CurrentTenant, body: BatchReleaseIn
) -> Any:
    """Release several holds at once (release reason code required)."""
    _need(ctx, "mes.exec:hold")
    return svc.release_batch(
        session, ctx.id, body.hold_ids, ctx.user, body.reason_id, body.comment
    )


@router.post("/holds/{hold_id}/release")
def hold_release(
    session: SessionDep, ctx: CurrentTenant, hold_id: uuid.UUID, body: ReleaseIn
) -> Any:
    _need(ctx, "mes.exec:hold")
    lot = svc.release_hold(
        session, ctx.id, hold_id, ctx.user, body.reason_id, body.comment
    )
    return serialize(
        session,
        ctx.id,
        ENTITIES["lot"],
        [one(session, ctx.id, "lot", lot["id"]) or lot],
    )[0]


class SplitChildIn(BaseModel):
    unit_ids: list[uuid.UUID] = Field(default_factory=list)
    qty: int | None = None
    carrier_id: uuid.UUID | None = None


class SplitIn(BaseModel):
    children: list[SplitChildIn] = Field(default_factory=list, max_length=50)
    comment: str | None = Field(default=None, max_length=300)
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)
    preview: bool = False


class MergeIn(BaseModel):
    source_lot_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    comment: str | None = Field(default=None, max_length=300)
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)
    preview: bool = False


def _sm_perm(ctx: TenantContext, p: str, body: SplitIn | MergeIn) -> None:
    _need(ctx, "mes.exec:read" if body.preview else p)
    if body.override and not body.preview:
        _need(ctx, "mes.exec:override")


@router.post("/lots/{lot_id}/split")
def lot_split(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: SplitIn
) -> Any:
    _sm_perm(ctx, "mes.exec:split", body)
    return sm.split(session, ctx.id, lot_id, body.model_dump(), ctx.user)


@router.post("/lots/{lot_id}/merge")
def lot_merge(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: MergeIn
) -> Any:
    _sm_perm(ctx, "mes.exec:merge", body)
    return sm.merge(session, ctx.id, lot_id, body.model_dump(), ctx.user)


class JumpIn(BaseModel):
    to_step_id: uuid.UUID
    reason_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=300)
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)


def _window(
    date_from: date | None, date_to: date | None, days: int
) -> tuple[datetime, datetime]:
    """统计区间 [起始日 00:00, 结束日次日 00:00)（服务器时区），默认最近 ``days`` 天。"""
    tz = datetime.now().astimezone().tzinfo
    end_d = date_to or datetime.now(tz).date()
    start_d = date_from or end_d - timedelta(days=days - 1)
    if start_d > end_d:
        raise HTTPException(status_code=422, detail="date_from after date_to")
    if (end_d - start_d).days > 366:
        raise HTTPException(status_code=422, detail="range too long (max 366 days)")
    return (
        datetime.combine(start_d, time.min, tz),
        datetime.combine(end_d + timedelta(days=1), time.min, tz),
    )


@router.get("/reports/wip")
def report_wip(
    session: SessionDep,
    ctx: CurrentTenant,
    product_id: uuid.UUID | None = None,
    lot_type_id: uuid.UUID | None = None,
    route_id: uuid.UUID | None = None,
) -> Any:
    """WIP summary by status / step / product, with lot aging (optional filters)."""
    _need(ctx, "mes.exec:read")
    return svc.wip_summary(
        session,
        ctx.id,
        product_id=product_id,
        lot_type_id=lot_type_id,
        route_id=route_id,
    )


@router.get("/reports/output")
def report_output(
    session: SessionDep,
    ctx: CurrentTenant,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Any:
    """Daily moves / output / scrap."""
    _need(ctx, "mes.exec:read")
    a, b = _window(date_from, date_to, 7)
    return {"data": svc.daily_output(session, ctx.id, a, b)}


@router.get("/reports/oee")
def report_oee(
    session: SessionDep,
    ctx: CurrentTenant,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Any:
    """Equipment OEE (availability × performance × quality) over the window."""
    _need(ctx, "mes.exec:read")
    a, b = _window(date_from, date_to, 7)
    return {"data": svc.oee(session, ctx.id, a, b), "from": a, "to": b}


@router.get("/reports/oee-trend")
def report_oee_trend(
    session: SessionDep,
    ctx: CurrentTenant,
    date_from: date | None = None,
    date_to: date | None = None,
    workcenter: str | None = None,
) -> Any:
    """Daily OEE trend (availability, quality, loading-weighted OEE)."""
    _need(ctx, "mes.exec:read")
    a, b = _window(date_from, date_to, 7)
    if (b - a).days > 92:
        raise HTTPException(status_code=422, detail="range too long (max 92 days)")
    return {"data": svc.oee_trend(session, ctx.id, a, b, workcenter)}


@router.get("/trace")
def trace(
    session: SessionDep,
    ctx: CurrentTenant,
    kind: Literal["lot", "wafer", "equipment", "material_lot"],
    code: str,
) -> Any:
    """Traceability: backward (sources, equipment, materials) and forward (outputs)."""
    _need(ctx, "mes.exec:read")
    return svc.trace(session, ctx.id, kind, code)


@router.get("/wafers/{wafer_id}/history")
def wafer_history(session: SessionDep, ctx: CurrentTenant, wafer_id: uuid.UUID) -> Any:
    """Wafer-level history (unit records plus lot records of the lots it was in)."""
    _need(ctx, "mes.exec:read")
    return {"data": svc.wafer_history(session, ctx.id, wafer_id)}


@router.get("/lots/{lot_id}/wafer-map")
def wafer_map(session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID) -> Any:
    """Wafer map: slots of the lot's carrier with wafer status."""
    _need(ctx, "mes.exec:read")
    return svc.wafer_map(session, ctx.id, lot_id)


@router.get("/qtime/monitor")
def qtime_monitor(session: SessionDep, ctx: CurrentTenant) -> Any:
    """Q-Time monitor: running clocks of waiting lots at their current step."""
    _need(ctx, "mes.exec:read")
    return {"data": svc.qtime_monitor(session, ctx.id)}


@router.get("/queue")
def dispatch_queue(
    session: SessionDep,
    ctx: CurrentTenant,
    q: str | None = None,
    lot_status: str | None = None,
    operation_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    on_hold: bool | None = None,
) -> Any:
    """Dispatch queue: active lots ordered by hold / priority / Q-Time / aging."""
    _need(ctx, "mes.exec:read")
    return {
        "data": dispatch.queue(
            session,
            ctx.id,
            q=q,
            lot_status=lot_status,
            operation_id=operation_id,
            product_id=product_id,
            on_hold=on_hold,
        )
    }


@router.get("/home")
def home_summary(session: SessionDep, ctx: CurrentTenant) -> Any:
    """Home KPIs: WIP, holds, Q-Time, equipment states, PM due, today's track-outs."""
    _need(ctx, "mes.exec:read")
    return dispatch.home(session, ctx.id)


@router.post("/qtime/sweep")
def qtime_sweep(session: SessionDep, ctx: CurrentTenant) -> Any:
    """Apply Q-Time violation actions (auto hold, ...) to waiting lots now."""
    _need(ctx, "mes.exec:hold")
    return svc.sweep_qtime(session, ctx.id, ctx.user)


@router.post("/lots/{lot_id}/jump")
def lot_jump(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: JumpIn
) -> Any:
    """Jump a waiting lot to another step of the same route (reason required)."""
    _need(ctx, "mes.exec:jump")
    if body.override:
        _need(ctx, "mes.exec:override")
    return svc.jump(session, ctx.id, lot_id, body.model_dump(), ctx.user)


class AdjustIn(BaseModel):
    kind: Literal["scrap", "bonus"]
    qty: int | None = Field(default=None, ge=1)
    unit_ids: list[uuid.UUID] | None = Field(default=None, max_length=1000)
    reason_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=300)
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)


@router.post("/lots/{lot_id}/adjust")
def lot_adjust(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: AdjustIn
) -> Any:
    """In-process scrap / bonus with a reason code."""
    _need(ctx, "mes.exec:adjust")
    if body.override:
        _need(ctx, "mes.exec:override")
    return svc.adjust(session, ctx.id, lot_id, body.model_dump(), ctx.user)


@router.post("/lots/{lot_id}/{stage}")
def lot_stage(
    session: SessionDep,
    ctx: CurrentTenant,
    lot_id: uuid.UUID,
    stage: Stage,
    body: StageIn,
) -> Any:
    _need(ctx, "mes.exec:write")
    if body.override:
        _need(ctx, "mes.exec:override")
    return svc.run_stage(session, ctx.id, lot_id, stage, body.model_dump(), ctx.user)
