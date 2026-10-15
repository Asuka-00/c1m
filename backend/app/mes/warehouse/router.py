"""入库单接口：状态迁移（提交 / 退回 / 确认 / 取消）与批次可入库数量查询。

权限：mes.wh:write（提交 / 取消）、mes.wh:confirm（确认 / 退回）。
入库单及明细的普通 CRUD 走通用接口 /mes/receipt、/mes/receipt-line。
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.deps import SessionDep
from app.core.schemas import StrictBody
from app.core.spec.serialize import serialize
from app.mes.warehouse import service as svc
from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext

router = APIRouter(prefix="/mes/receipt", tags=["mes"])

#: 动作 -> 所需权限
NEED = {
    "submit": "mes.wh:write",
    "cancel": "mes.wh:write",
    "confirm": "mes.wh:confirm",
    "reject": "mes.wh:confirm",
}


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise HTTPException(status_code=403, detail="Not enough permissions")


class TransitionIn(StrictBody):
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
