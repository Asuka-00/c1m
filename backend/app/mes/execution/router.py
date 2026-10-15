"""批次执行接口：阶段作业、检查预览、Hold、拆合批。

权限：mes.exec:read（上下文 / 预览）、mes.exec:write（阶段作业）、mes.exec:override
（强制放行阻断检查，须填原因）、mes.exec:hold（手工 Hold / 释放）、mes.exec:split / mes.exec:merge、
mes.exec:jump（跳站）、mes.exec:adjust（在制报废 / 补数）。
阶段被阻断时返回 409 ``{"detail": {"code": "check_blocked", "results": [...]}}``。
"""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.core.deps import SessionDep
from app.core.models import iso_utc
from app.core.schemas import NoBody
from app.core.spec.engine import ENTITIES
from app.core.spec.errors import err_422, http_422, query_422
from app.core.spec.excel import tenant_tz
from app.core.spec.qdates import (
    DateQ,
    DateTimeQ,
    check_range,
    parse_date,
    parse_datetime,
)
from app.core.spec.serialize import serialize
from app.mes.common import idempotency as idem
from app.mes.common.guard import perm_body
from app.mes.common.query import one
from app.mes.common.sitedate import site_today
from app.mes.execution import bin_split as bin_split_svc
from app.mes.execution import ct_move as ct_move_svc
from app.mes.execution import dispatch, shift_log, transform_undo
from app.mes.execution import operator_qual as oq
from app.mes.execution import service as sm
from app.mes.execution import service as svc
from app.mes.execution import transform as transform_svc
from app.mes.execution.checks.registry import overall_overridable
from app.mes.lot.service import lookup_customer_lots
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/exec", tags=["mes"])
Stage = Literal["move_in", "track_in", "track_out", "move_out"]


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise HTTPException(status_code=403, detail="Not enough permissions")


class DcIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    measurement_item_id: uuid.UUID
    unit_id: uuid.UUID | None = None
    site_no: int = Field(default=1, ge=1)
    value: float | None = None


class ScrapIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    reason_id: uuid.UUID
    unit_id: uuid.UUID | None = None
    qty: int | None = Field(default=None, ge=1)


class ReworkUnitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    reason_id: uuid.UUID
    unit_id: uuid.UUID


class StageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    equipment_id: uuid.UUID | None = None
    recipe_id: uuid.UUID | None = None
    eqp_recipe: str | None = Field(default=None, max_length=200)
    reticle_id: uuid.UUID | None = None
    carrier_id: uuid.UUID | None = None
    tool_ids: list[uuid.UUID] | None = None
    chamber_ids: list[uuid.UUID] | None = None
    material_lot_ids: list[uuid.UUID] | None = None
    dc: list[DcIn] | None = None
    scrap: list[ScrapIn] | None = None
    rework_units: list[ReworkUnitIn] | None = None
    branch: bool = False
    rework: bool = False
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)


class HoldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    reason_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=300)


class ReleaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
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


@router.get("/lots/{lot_id}/bom-usage")
def lot_bom_usage(session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID) -> Any:
    """BOM usage of a lot: cumulative normal consumption vs plan per issue line."""
    _need(ctx, "mes.exec:read")
    return svc.lot_bom_usage(session, ctx.id, lot_id)


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
    res = svc.preview(session, ctx.id, lot_id, stage, body.model_dump(), ctx.user)
    return {"results": res, "overridable": overall_overridable(res)}


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
    date_from: DateTimeQ = None,
    date_to: DateTimeQ = None,
    reason: str | None = None,
    product: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=5000),
    sort_by: str = "held_at",
    sort_order: Literal["asc", "desc"] = "desc",
    include_terminal: bool = False,
) -> Any:
    """Hold 管理页列表：服务端筛选、搜索、排序与分页，返回 ``{data, count}``。"""
    _need(ctx, "mes.exec:read")
    df = parse_datetime("date_from", date_from)
    dt = parse_datetime("date_to", date_to)
    check_range("date_from", df, dt)
    rows = svc.list_holds(
        session,
        ctx.id,
        {"active": True, "released": False}.get(status),
        reason_id,
        source,
        product_id,
        df,
        dt,
        include_terminal=include_terminal,
    )
    if reason:
        rows = [r for r in rows if r["reason"] == reason]
    if product:
        rows = [r for r in rows if r["product"] == product]
    if q:
        k = q.strip().lower()
        keys = ("lot", "product", "reason", "reason_name", "comment", "held_by")
        rows = [r for r in rows if any(k in str(r.get(f) or "").lower() for f in keys)]
    if rows and sort_by in rows[0]:
        rows.sort(
            key=lambda r: (
                r.get(sort_by) is None,
                r.get(sort_by) if r.get(sort_by) is not None else 0,
            ),
            reverse=sort_order == "desc",
        )
    start = (page - 1) * page_size
    return {"data": rows[start : start + page_size], "count": len(rows)}


@router.get("/holds/{hold_id}")
def hold_detail(session: SessionDep, ctx: CurrentTenant, hold_id: uuid.UUID) -> Any:
    """Hold 详情：字段同列表每条（含 Q-Time 附加字段，D20）。"""
    _need(ctx, "mes.exec:read")
    return svc.get_hold(session, ctx.id, hold_id)


class BatchReleaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
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
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    unit_ids: list[uuid.UUID] = Field(default_factory=list)
    qty: int | None = None
    carrier_id: uuid.UUID | None = None


class SplitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    children: list[SplitChildIn] = Field(default_factory=list, max_length=50)
    comment: str | None = Field(default=None, max_length=300)
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)
    preview: bool = False


class MergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
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
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    to_step_id: uuid.UUID
    reason_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=300)
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)


def _window(
    s: Session,
    tid: uuid.UUID,
    date_from_raw: str | None,
    date_to_raw: str | None,
    days: int,
) -> tuple[datetime, datetime]:
    """统计区间 [起始日 00:00, 结束日次日 00:00)（站点时区，D75），默认最近 ``days`` 天。

    返回带站点时区的时间（与 UTC 为同一时刻），报表按该时区分日。
    """
    # D77 补充三：先查格式（严格 YYYY-MM-DD → 否则 value_error/pattern），再查 range_inverted
    date_from = parse_date("date_from", date_from_raw)
    date_to = parse_date("date_to", date_to_raw)
    tz = tenant_tz(s, tid)
    end_d = date_to or site_today(s, tid)
    start_d = date_from or end_d - timedelta(days=days - 1)
    if start_d > end_d:
        raise err_422(
            ["query", "date_from"],
            "date_from after date_to",
            "value_error",
            {"reason": "range_inverted"},
        )
    if (end_d - start_d).days > 366:
        raise err_422(
            ["query", "date_to"],
            "range too long (max 366 days)",
            "date_range_too_large",
            {"max_days": 366},
        )
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
    date_from: DateQ = None,
    date_to: DateQ = None,
) -> Any:
    """Daily moves / output / scrap."""
    _need(ctx, "mes.exec:read")
    a, b = _window(session, ctx.id, date_from, date_to, 7)
    return {"data": svc.daily_output(session, ctx.id, a, b)}


@router.get("/reports/oee")
def report_oee(
    session: SessionDep,
    ctx: CurrentTenant,
    date_from: DateQ = None,
    date_to: DateQ = None,
) -> Any:
    """Equipment OEE (availability × performance × quality) over the window."""
    _need(ctx, "mes.exec:read")
    a, b = _window(session, ctx.id, date_from, date_to, 7)
    return {
        "data": svc.oee(session, ctx.id, a, b),
        "from": iso_utc(a),
        "to": iso_utc(b),
    }


@router.get("/reports/yield")
def report_yield(
    session: SessionDep,
    ctx: CurrentTenant,
    date_from: DateQ = None,
    date_to: DateQ = None,
    group: Literal["operation", "product", "lot"] = "operation",
) -> Any:
    """Yield by operation / product / lot and scrap reason Pareto."""
    _need(ctx, "mes.exec:read")
    a, b = _window(session, ctx.id, date_from, date_to, 30)
    return {
        **svc.yield_report(session, ctx.id, a, b, group),
        "from": iso_utc(a),
        "to": iso_utc(b),
    }


@router.get("/reports/oee-trend")
def report_oee_trend(
    session: SessionDep,
    ctx: CurrentTenant,
    date_from: DateQ = None,
    date_to: DateQ = None,
    workcenter: str | None = None,
) -> Any:
    """Daily OEE trend (availability, quality, loading-weighted OEE)."""
    _need(ctx, "mes.exec:read")
    a, b = _window(session, ctx.id, date_from, date_to, 7)
    if (b - a).days > 92:
        raise err_422(
            ["query", "date_to"],
            "range too long (max 92 days)",
            "date_range_too_large",
            {"max_days": 92},
        )
    return {"data": svc.oee_trend(session, ctx.id, a, b, workcenter)}


def _req_date(name: str, v: str | None) -> date:
    """必填日期（D77 补充三）：严格 YYYY-MM-DD，错误 ctx.reason=pattern。"""
    d = parse_date(name, v)
    if d is None:
        raise err_422(["query", name], "Field required", "missing")
    return d


def _opt_ref(s: Session, tid: uuid.UUID, name: str, code: str, v: str | None) -> Any:
    if v is None or v == "":
        return None
    try:
        rid = uuid.UUID(v)
    except ValueError:
        raise err_422(
            ["query", name], "must be a uuid", "value_error", input=v
        ) from None
    if one(s, tid, code, rid) is None:  # 不存在或跨租户
        raise HTTPException(
            status_code=404,
            detail={"code": f"{code}_not_found", "message": f"{code} not found"},
        )
    return rid


@router.get("/reports/ct-move")
def report_ct_move(
    session: SessionDep,
    ctx: CurrentTenant,
    date_from: DateQ = None,
    date_to: DateQ = None,
    operation_id: str | None = None,
    product_id: str | None = None,
) -> Any:
    """CT / Move 报表（D73）：按站点日趋势、按工序明细与合计。"""
    _need(ctx, "mes.exec:read")
    a = _req_date("date_from", date_from)
    b = _req_date("date_to", date_to)
    if a > b:
        raise err_422(
            ["query", "date_from"],
            "date_from after date_to",
            "value_error",
            {"reason": "range_inverted"},
        )
    if (b - a).days + 1 > ct_move_svc.MAX_DAYS:
        raise err_422(
            ["query", "date_to"],
            f"range too long (max {ct_move_svc.MAX_DAYS} days)",
            "date_range_too_large",
            {"max_days": ct_move_svc.MAX_DAYS},
        )
    op = _opt_ref(session, ctx.id, "operation_id", "operation", operation_id)
    prod = _opt_ref(session, ctx.id, "product_id", "product", product_id)
    return ct_move_svc.ct_move(session, ctx.id, a, b, op, prod)


@router.get("/trace")
def trace(
    session: SessionDep,
    ctx: CurrentTenant,
    kind: str,
    code: str,
) -> Any:
    """Traceability: backward (sources, equipment, materials) and forward (outputs)."""
    _need(ctx, "mes.exec:read")
    return svc.trace(session, ctx.id, kind, code)


@router.get("/customer-lots")
def customer_lots(
    session: SessionDep,
    ctx: CurrentTenant,
    customer_lot_no: str | None = Query(None, min_length=1, max_length=100),
    lot_no: str | None = Query(None, min_length=1, max_length=100),
) -> Any:
    """B7: look up internal lot numbers by customer lot no., or the reverse."""
    _need(ctx, "mes.exec:read")
    if not customer_lot_no and not lot_no:
        raise query_422([("customer_lot_no", "customer_lot_no or lot_no required")])
    return {"data": lookup_customer_lots(session, ctx.id, customer_lot_no, lot_no)}


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
def qtime_sweep(
    session: SessionDep, ctx: CurrentTenant, _body: NoBody | None = None
) -> Any:
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
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
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


class ShiftLogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    shift_date: date
    shift_id: uuid.UUID
    area_id: uuid.UUID | None = None
    summary: str = Field(max_length=4000)
    open_items: str | None = Field(default=None, max_length=4000)


class AckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    comment: str | None = Field(default=None, max_length=300)


@router.get("/shift-logs")
def shift_logs(
    session: SessionDep,
    ctx: CurrentTenant,
    date_from: DateQ = None,
    date_to: DateQ = None,
) -> Any:
    """Shift handover logs in a date range."""
    _need(ctx, "mes.exec:read")
    df = parse_date("date_from", date_from)
    dt = parse_date("date_to", date_to)
    check_range("date_from", df, dt)
    return {"data": shift_log.list_logs(session, ctx.id, df, dt)}


@router.post("/shift-logs")
def shift_log_create(session: SessionDep, ctx: CurrentTenant, body: ShiftLogIn) -> Any:
    """Hand over a shift."""
    _need(ctx, "mes.exec:write")
    return shift_log.create(session, ctx.id, body.model_dump(), ctx.user)


@router.post("/shift-logs/{rid}/ack")
def shift_log_ack(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: AckIn
) -> Any:
    """Acknowledge a shift handover."""
    _need(ctx, "mes.exec:write")
    return shift_log.acknowledge(session, ctx.id, rid, body.model_dump(), ctx.user)


class PriorityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    priority_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=300)
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)


@router.post("/lots/{lot_id}/priority")
def lot_priority(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: PriorityIn
) -> Any:
    """Change a lot's priority (hot lot)."""
    _need(ctx, "mes.exec:adjust")
    if body.override:
        _need(ctx, "mes.exec:override")
    return svc.set_priority(session, ctx.id, lot_id, body.model_dump(), ctx.user)


class CarrierChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    carrier_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=300)


class CommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    comment: str | None = Field(default=None, max_length=300)


@router.get("/carriers/board")
def carrier_board(session: SessionDep, ctx: CurrentTenant) -> Any:
    """Carrier overview: lot, fill, usage and cleaning due."""
    _need(ctx, "mes.exec:read")
    return {"data": svc.carrier_board(session, ctx.id)}


@router.post("/carriers/{carrier_id}/clean")
def carrier_clean(
    session: SessionDep, ctx: CurrentTenant, carrier_id: uuid.UUID, body: CommentIn
) -> Any:
    """Mark a carrier as cleaned."""
    _need(ctx, "mes.exec:write")
    return svc.clean_carrier(session, ctx.id, carrier_id, ctx.user, body.comment)


class SortSlotIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    wafer_id: uuid.UUID
    slot: int = Field(ge=1)


class SortIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # D65：多余字段 422 unknown_field
    slots: list[SortSlotIn] = Field(min_length=1, max_length=50)
    carrier_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=300)
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)


@router.post("/lots/{lot_id}/sort")
def lot_sort(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: SortIn
) -> Any:
    """Wafer sorter: reorder slots or move the lot to another carrier."""
    _need(ctx, "mes.exec:write")
    if body.override:
        _need(ctx, "mes.exec:override")
    return svc.sort_wafers(session, ctx.id, lot_id, body.model_dump(), ctx.user)


@router.post("/lots/{lot_id}/carrier")
def lot_carrier_change(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: CarrierChangeIn
) -> Any:
    """Move a lot's wafers into another carrier."""
    _need(ctx, "mes.exec:write")
    return svc.change_carrier(session, ctx.id, lot_id, body.model_dump(), ctx.user)


@router.post("/lots/{lot_id}/{stage}")
def lot_stage(
    session: SessionDep,
    ctx: CurrentTenant,
    lot_id: uuid.UUID,
    stage: Stage,
    body: StageIn,
    idempotency_key: Annotated[str | None, Header(alias=idem.HEADER)] = None,
) -> Any:
    """Lot stage step. Idempotency-Key (D57 / #IK01): same key + same body replays
    the first response; different body 422 idempotency_key_reused."""
    _need(ctx, "mes.exec:write")
    if body.override:
        _need(ctx, "mes.exec:override")
    data = body.model_dump()
    return idem.run(
        session,
        ctx.id,
        ctx.user,
        "POST /mes/exec/lots/{lot_id}/{stage}",
        idempotency_key,
        {"lot_id": lot_id, "stage": stage, **data},
        lambda: svc.run_stage(session, ctx.id, lot_id, stage, data, ctx.user),
    )


@router.get("/batch/{stage}/candidates")
def batch_candidates(
    session: SessionDep,
    ctx: CurrentTenant,
    stage: Literal["track_in", "track_out"],
    equipment_id: uuid.UUID,
) -> Any:
    """Lots on one tool ready for batch track in / out."""
    _need(ctx, "mes.exec:read")
    return svc.batch_candidates(session, ctx.id, stage, equipment_id)


class BatchStageIn(StageIn):
    lot_ids: list[uuid.UUID] = Field(min_length=2, max_length=25)


@router.post("/batch/{stage}")
def batch_stage(
    session: SessionDep,
    ctx: CurrentTenant,
    stage: Literal["track_in", "track_out"],
    body: BatchStageIn,
) -> Any:
    """Track in / out several lots together on one tool."""
    _need(ctx, "mes.exec:write")
    if body.override:
        _need(ctx, "mes.exec:override")
    return svc.batch_stage(session, ctx.id, stage, body.model_dump(), ctx.user)


# ---------------- 单位转换（B5） ----------------
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TransformSourceIn(_Strict):
    wafer_id: uuid.UUID
    qty: int = Field(ge=1)


class TransformOutputIn(_Strict):
    product_id: uuid.UUID
    route_id: uuid.UUID
    track_unit_kind: Literal["die", "strip", "package", "unit"]
    qty: int | None = Field(default=None, ge=1)
    sources: list[TransformSourceIn] = Field(min_length=1, max_length=500)


class ManualGoodIn(_Strict):
    wafer_id: uuid.UUID
    good_qty: int = Field(ge=0)
    fail_qty: int = Field(default=0, ge=0)


class TransformIn(_Strict):
    """单位转换请求（严格载荷；source / external_event_id 等未知字段 422）。"""

    transform_type: Literal["dicing", "die_attach", "singulation"]
    input_lot_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    outputs: list[TransformOutputIn] = Field(min_length=1, max_length=50)
    manual_good: list[ManualGoodIn] | None = Field(default=None, max_length=500)
    reason_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=300)


TransformBody = Annotated[
    TransformIn, Depends(perm_body("mes.exec:transform", TransformIn))
]


@router.post("/transform/preview")
def transform_preview(
    session: SessionDep, ctx: CurrentTenant, body: TransformBody
) -> Any:
    """Validate a unit transform: per-wafer good qty (map / manual / gross die),
    allocation and conservation; nothing is written."""
    return transform_svc.preview(session, ctx.id, body.model_dump())


@router.post("/transform")
def transform(session: SessionDep, ctx: CurrentTenant, body: TransformBody) -> Any:
    """Unit transform (dicing / die attach / singulation), whole lots, multi-in
    multi-out; parents become converted, children start on their own route."""
    return transform_svc.transform(session, ctx.id, body.model_dump(), ctx.user)


class TransformUndoIn(_Strict):
    """撤销单位转换（严格载荷；空请求体 / {} 也可以）。"""

    reason_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=300)


@router.post("/transform/{transform_id}/undo")
def transform_undo_(
    session: SessionDep,
    ctx: CurrentTenant,
    transform_id: uuid.UUID,
    body: Annotated[
        TransformUndoIn | None,
        Depends(perm_body("mes.exec:transform", TransformUndoIn, optional=True)),
    ],
) -> Any:
    """Undo a unit transform / bin split while every child lot is still untouched
    (waiting, not on hold, no later transactions); 409 transform_undo_blocked
    otherwise. Parents return to their pre-transform status."""
    data = body.model_dump() if body else {}
    if data.get("reason_id") and not one(
        session, ctx.id, "reason_code", data["reason_id"]
    ):
        raise http_422([(("reason_id",), "reason not found")])
    return transform_undo.undo(session, ctx.id, transform_id, data, ctx.user)


# ---------------- 按 bin 拆批（B8） ----------------
class BinQtyIn(_Strict):
    bin_code: str = Field(min_length=1, max_length=32)
    qty: int = Field(ge=0)


class ManualBinsIn(_Strict):
    wafer_id: uuid.UUID
    bins: list[BinQtyIn] = Field(min_length=1, max_length=500)


class BinOutputIn(_Strict):
    bin_codes: list[str] = Field(min_length=1, max_length=100)
    product_id: uuid.UUID | None = None
    route_id: uuid.UUID | None = None


class BinSplitIn(_Strict):
    """按 bin 拆批请求（严格载荷；source / external_event_id 等未知字段 422）。"""

    input_lot_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    outputs: list[BinOutputIn] | None = Field(default=None, max_length=100)
    manual_bins: list[ManualBinsIn] | None = Field(default=None, max_length=500)
    reason_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=300)


BinSplitBody = Annotated[
    BinSplitIn, Depends(perm_body("mes.exec:transform", BinSplitIn))
]


@router.post("/bin-split/preview")
def bin_split_preview(
    session: SessionDep, ctx: CurrentTenant, body: BinSplitBody
) -> Any:
    """Validate a bin split: per-wafer bin quantities (map / manual), excluded bins
    by bin_type, conservation and child lot quantities; nothing is written."""
    return bin_split_svc.preview(session, ctx.id, body.model_dump())


@router.post("/bin-split")
def bin_split(session: SessionDep, ctx: CurrentTenant, body: BinSplitBody) -> Any:
    """Split whole lots into child lots by bin code (unit transform bin_split)."""
    return bin_split_svc.bin_split(session, ctx.id, body.model_dump(), ctx.user)


# ---------------- P3-B6 人员资质（D74） ----------------
def _int_q(name: str, raw: str | None, lo: int, hi: int) -> int | None:
    """可选整数查询参数：非整数或越界 → 422 value_error（ctx 带 min / max）。"""
    if raw is None or raw == "":
        return None
    v = raw.strip()
    if not v.lstrip("-").isdigit() or not lo <= int(v) <= hi:
        raise err_422(
            ["query", name],
            f"{name}: integer {lo}-{hi}",
            "value_error",
            {"min": lo, "max": hi},
            input=raw,
        )
    return int(v)


@router.get("/operator-qual/expiring")
def operator_qual_expiring(
    session: SessionDep,
    ctx: CurrentTenant,
    days: str | None = Query(
        None, json_schema_extra={"type": "integer", "minimum": 1, "maximum": 365}
    ),
) -> Any:
    """Qualifications expiring within ``days`` (default: warn_days setting), active
    and not permanent only; sorted by days_left, then username (D64/D74)."""
    _need(ctx, "mes.exec:read")
    return oq.expiring(session, ctx.id, _int_q("days", days, 1, 365))


@router.get("/operator-qual/{qual_id}/history")
def operator_qual_history(
    session: SessionDep,
    ctx: CurrentTenant,
    qual_id: uuid.UUID,
    limit: str | None = Query(None, json_schema_extra={"type": "integer"}),
    offset: str | None = Query(None, json_schema_extra={"type": "integer"}),
) -> Any:
    """Qualification change history, newest first (D74). 403 before 404."""
    _need(ctx, "mes.exec:read")
    lim = _int_q("limit", limit, 1, 200) or 50
    off = _int_q("offset", offset, 0, 10**9) or 0
    if not one(session, ctx.id, "operator_qual", qual_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "operator qualification not found"},
        )
    return oq.history(session, ctx.id, qual_id, lim, off)
