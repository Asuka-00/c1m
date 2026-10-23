"""入库单与领料单接口：状态迁移、批次可入库数量查询、工单物料需求查询。

权限：mes.wh:write（提交 / 取消）、mes.wh:confirm（确认 / 退回）。
入库单及明细的普通 CRUD 走通用接口 /mes/receipt、/mes/receipt-line；
领料单同理走 /mes/material-issue、/mes/material-issue-line。
"""

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core import error_codes as ec
from app.core.deps import SessionDep
from app.core.spec.errors import coded
from app.core.spec.serialize import serialize
from app.mes.warehouse import inbound as inbound_svc
from app.mes.warehouse import issue as issue_svc
from app.mes.warehouse import service as svc
from app.mes.warehouse import shipment as shipment_svc
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/receipt", tags=["mes"])
issue_router = APIRouter(prefix="/mes/material-issue", tags=["mes"])
shipment_router = APIRouter(prefix="/mes/shipment", tags=["mes"])
inbound_router = APIRouter(prefix="/mes/material-receipt", tags=["mes"])

#: 动作 -> 所需权限
NEED = {
    "submit": "mes.wh:write",
    "cancel": "mes.wh:write",
    "confirm": "mes.wh:confirm",
    "reject": "mes.wh:confirm",
}


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise coded(403, ec.PERMISSION_DENIED, "Not enough permissions")


class TransitionIn(BaseModel):
    action: str


@router.post("/{rid}/transition")
def receipt_transition(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: TransitionIn
) -> Any:
    """submit | reject | confirm | cancel."""
    _need(ctx, NEED.get(body.action, "mes.wh:write"))
    row = svc.transition(session, ctx.id, rid, body.action, ctx.user)
    return serialize(session, ctx.id, svc.RECEIPT, [row])[0]


@router.get("/receivable/{lot_id}")
def lot_receivable(session: SessionDep, ctx: CurrentTenant, lot_id: uuid.UUID) -> Any:
    """Quantity of a lot still open for receipt."""
    _need(ctx, "mes.wh:read")
    return svc.receivable(session, ctx.id, lot_id)


@issue_router.post("/{iid}/transition")
def issue_transition(
    session: SessionDep, ctx: CurrentTenant, iid: uuid.UUID, body: TransitionIn
) -> Any:
    """confirm | cancel."""
    _need(ctx, NEED.get(body.action, "mes.wh:write"))
    row = issue_svc.transition(session, ctx.id, iid, body.action, ctx.user)
    return serialize(session, ctx.id, issue_svc.ISSUE, [row])[0]


@issue_router.get("/requirements/{wo_id}")
def issue_requirements(
    session: SessionDep, ctx: CurrentTenant, wo_id: uuid.UUID
) -> Any:
    """Material requirement of a work order (from its BOM) against what was issued."""
    _need(ctx, "mes.wh:read")
    return issue_svc.requirements(session, ctx.id, wo_id)


@shipment_router.post("/{sid}/transition")
def shipment_transition(
    session: SessionDep, ctx: CurrentTenant, sid: uuid.UUID, body: TransitionIn
) -> Any:
    """confirm | cancel."""
    _need(ctx, NEED.get(body.action, "mes.wh:write"))
    row = shipment_svc.transition(session, ctx.id, sid, body.action, ctx.user)
    return serialize(session, ctx.id, shipment_svc.SHIPMENT, [row])[0]


@inbound_router.post("/{rid}/transition")
def inbound_transition(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: TransitionIn
) -> Any:
    """confirm | cancel."""
    _need(ctx, NEED.get(body.action, "mes.wh:write"))
    row = inbound_svc.transition(session, ctx.id, rid, body.action, ctx.user)
    return serialize(session, ctx.id, inbound_svc.RECEIPT, [row])[0]


class IqcIn(BaseModel):
    result: str


@inbound_router.post("/lines/{line_id}/iqc")
def inbound_iqc(
    session: SessionDep, ctx: CurrentTenant, line_id: uuid.UUID, body: IqcIn
) -> Any:
    """IQC verdict for one received line: pass | fail."""
    _need(ctx, "mes.wh:confirm")
    row = inbound_svc.iqc(session, ctx.id, line_id, body.result, ctx.user)
    return serialize(session, ctx.id, inbound_svc.LINE, [row])[0]
