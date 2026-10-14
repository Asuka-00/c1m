"""工艺专用接口（通用 CRUD 见 mes.common.router）。"""

import uuid
from typing import Any

from fastapi import APIRouter

from app.core.deps import SessionDep
from app.core.schemas import NoBody, StrictBody
from app.mes.common.query import jsonable
from app.mes.common.router import require_entity
from app.mes.process import ecn
from app.mes.process.routing import reorder_steps
from app.platform.auth.deps import CurrentTenant

router = APIRouter(prefix="/mes", tags=["mes"])


class ReorderIn(StrictBody):
    step_ids: list[uuid.UUID]


@router.post("/route/{rid}/reorder")
def route_reorder(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: ReorderIn
) -> Any:
    """Renumber a draft route's steps (10, 20, 30, ...) in the given order."""
    e = require_entity(ctx, "route_step", "write")
    return {"data": reorder_steps(session, ctx.id, rid, body.step_ids, ctx.user, e)}


@router.post("/change-order/{cid}/release")
def change_release(
    session: SessionDep,
    ctx: CurrentTenant,
    cid: uuid.UUID,
    _body: NoBody | None = None,
) -> Any:
    """Release an engineering change (applies now when its effective time has come)."""
    require_entity(ctx, "change_order", "write")
    return {"data": jsonable(ecn.release(session, ctx.id, cid, ctx.user))}


@router.post("/change-order/{cid}/cancel")
def change_cancel(
    session: SessionDep,
    ctx: CurrentTenant,
    cid: uuid.UUID,
    _body: NoBody | None = None,
) -> Any:
    """Cancel an engineering change that has not taken effect."""
    require_entity(ctx, "change_order", "write")
    return {"data": jsonable(ecn.cancel(session, ctx.id, cid, ctx.user))}
