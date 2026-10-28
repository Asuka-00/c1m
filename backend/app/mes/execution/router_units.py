"""单元级与前后道交接接口：单元转换、芯片级芯片图、Bank 入库 / 领用、SPC 控制图。

权限：mes.exec:write（转换、导入芯片图）、mes.exec:bank（Bank 入库 / 领用）、mes.exec:read（查询）。
"""

import uuid
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core import error_codes as ec
from app.core.deps import SessionDep
from app.core.spec.errors import coded
from app.core.spec.excel import TEMPLATE_DIR
from app.mes.execution.bank import ops as bank
from app.mes.execution.units import convert as conv
from app.mes.execution.units import die_map
from app.mes.quality.service import spc_chart
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/exec", tags=["mes"])


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise coded(403, ec.PERMISSION_DENIED, "Not enough permissions")


class ConvertIn(BaseModel):
    to_kind: Literal["die", "strip", "package", "unit"]
    per_parent: int = Field(default=1, ge=1, le=100_000)
    per_child: int = Field(default=1, ge=1, le=100_000)
    use_map: bool = False
    comment: str | None = Field(default=None, max_length=300)
    override: bool = False
    override_reason: str | None = Field(default=None, max_length=300)
    preview: bool = False


@router.post("/lots/{lot_id}/convert")
def lot_convert(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: ConvertIn
) -> Any:
    """Convert all units of the lot to the next unit kind (wafer → die / strip / unit)."""
    _need(ctx, "mes.exec:read" if body.preview else "mes.exec:write")
    if body.override and not body.preview:
        _need(ctx, "mes.exec:override")
    return conv.convert(session, ctx.id, lot_id, body.model_dump(), ctx.user)


class DieMapIn(BaseModel):
    unit_id: uuid.UUID | None = None
    unit_code: str | None = Field(default=None, max_length=64)
    dies: list[list[int | str]] = Field(max_length=die_map.MAX_DIES)


class DieMapsIn(BaseModel):
    test_kind: Literal["cp", "aoi", "ink"] = "cp"
    route_step_id: uuid.UUID | None = None
    source: str | None = Field(default=None, max_length=200)
    maps: list[DieMapIn] = Field(min_length=1, max_length=50)


@router.post("/lots/{lot_id}/die-maps")
def die_maps_import(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: DieMapsIn
) -> Any:
    """Import die-level wafer maps ([x, y, bin] per die) for wafers of the lot."""
    _need(ctx, "mes.exec:write")
    return die_map.import_maps(session, ctx.id, lot_id, body.model_dump(), ctx.user)


@router.get("/die-maps/template")
def die_map_template(ctx: CurrentTenant) -> FileResponse:
    """Die map CSV template (``wafer,x,y,bin``)."""
    _need(ctx, "mes.exec:read")
    return FileResponse(
        TEMPLATE_DIR / "die_map.csv", media_type="text/csv", filename="die_map.csv"
    )


@router.get("/die-maps/{map_id}")
def die_map_detail(session: SessionDep, ctx: CurrentTenant, map_id: uuid.UUID) -> Any:
    """Die map with dies and a per-bin legend."""
    _need(ctx, "mes.exec:read")
    return die_map.get_map(session, ctx.id, map_id)


@router.get("/units/{unit_id}/die-maps")
def unit_die_maps(session: SessionDep, ctx: CurrentTenant, unit_id: uuid.UUID) -> Any:
    """Die maps of one wafer (latest first, without dies)."""
    _need(ctx, "mes.exec:read")
    return {"data": die_map.unit_maps(session, ctx.id, unit_id)}


class BankInIn(BaseModel):
    bank_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=300)


@router.post("/lots/{lot_id}/bank-in")
def lot_bank_in(
    session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID, body: BankInIn
) -> Any:
    """Put a completed lot into a wafer / die bank."""
    _need(ctx, "mes.exec:bank")
    return bank.bank_in(session, ctx.id, lot_id, body.model_dump(), ctx.user)


class BankPickIn(BaseModel):
    lot_id: uuid.UUID
    unit_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)
    qty: int | None = Field(default=None, ge=1)


class BankIssueIn(BaseModel):
    work_order_id: uuid.UUID
    lots: list[BankPickIn] = Field(min_length=1, max_length=50)
    comment: str | None = Field(default=None, max_length=300)


@router.post("/bank/issue")
def bank_issue(session: SessionDep, ctx: CurrentTenant, body: BankIssueIn) -> Any:
    """Issue banked lots (all or some units) into a new lot of a work order."""
    _need(ctx, "mes.exec:bank")
    return bank.bank_issue(session, ctx.id, body.model_dump(), ctx.user)


@router.get("/spc")
def spc(session: SessionDep, ctx: CurrentTenant, dc_plan_item_id: uuid.UUID) -> Any:
    """X-bar control chart of a DC plan item: limits and recent subgroups with rule hits."""
    _need(ctx, "mes.exec:read")
    out = spc_chart(session, ctx.id, dc_plan_item_id)
    if out is None:
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    return out
