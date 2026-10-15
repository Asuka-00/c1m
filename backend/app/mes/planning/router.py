"""工单接口：生命周期迁移与开批 / 撤销开批。

权限：mes.wo:release（状态迁移）、mes.lot:start（计划 / 开批 / 撤销）。
工单的普通 CRUD 走通用接口 /mes/work-order。
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.deps import SessionDep
from app.core.schemas import StrictBody
from app.core.spec.serialize import serialize
from app.mes.common.guard import perm_body
from app.mes.planning import board
from app.mes.planning import service as svc
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/work-order", tags=["mes"])


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise HTTPException(status_code=403, detail="Not enough permissions")


class TransitionIn(StrictBody):
    action: str


class PlanIn(StrictBody):
    lot_size: int | None = Field(default=None, ge=1)
    qty: int | None = Field(default=None, ge=0)


class LotIn(BaseModel):
    """开批的一个批次（D40 严格载荷：只接受下列字段，其余含旧的 carrier 一律 422；
    D41 加回 wafer_sources）。"""

    model_config = ConfigDict(extra="forbid")

    qty: int = Field(ge=1)
    carrier_id: uuid.UUID | None = None
    slots: list[int] | None = None
    source_ref: str | None = Field(default=None, max_length=100)
    # D41：按片指定来源（数量须等于 qty），每项与 source_ref 同长度上限
    wafer_sources: (
        list[Annotated[str, StringConstraints(max_length=100, strict=True)]] | None
    ) = Field(default=None, max_length=1000)
    # B7 客户来料
    customer_lot_no: str | None = Field(default=None, max_length=100)
    ownership: Literal["own", "customer"] | None = None
    customer_id: uuid.UUID | None = None


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lots: list[LotIn] = Field(min_length=1, max_length=50)


class UndoIn(StrictBody):
    lot_ids: list[uuid.UUID] | None = None


@router.get("/board")
def wo_board(
    session: SessionDep,
    ctx: CurrentTenant,
    warn_days: int | None = Query(None, ge=0, le=60),
) -> Any:
    """Work order progress board with due-date warnings."""
    _need(ctx, "mes.wo:read")
    return {
        "data": board.wo_board(
            session,
            ctx.id,
            board.warn_days(session, ctx.id) if warn_days is None else warn_days,
        )
    }


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
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[StartIn, Depends(perm_body("mes.lot:start", StartIn))],
) -> Any:
    """Start lots (D34: permission before body; D40: strict payload)."""
    lots = svc.start(
        session, ctx.id, rid, [x.model_dump() for x in body.lots], ctx.user
    )
    warnings = (
        [
            {
                "code": "no_active_bom",
                "message": "product has no active BOM; lots locked no BOM version",
            }
        ]
        if any(x.get("bom_id") is None for x in lots)
        else []
    )
    return {"data": serialize(session, ctx.id, svc.LOT, lots), "warnings": warnings}


@router.post("/{rid}/undo-start")
def wo_undo_start(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: UndoIn
) -> Any:
    """Allowed only while every selected lot still waits at the first step."""
    _need(ctx, "mes.lot:start")
    return {"undone": svc.undo_start(session, ctx.id, rid, body.lot_ids, ctx.user)}
