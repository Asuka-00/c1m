"""工艺专用接口（通用 CRUD 见 mes.common.router）。"""

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import SessionDep
from app.mes.common.router import require_entity
from app.mes.process.routing import reorder_steps
from app.platform.auth.deps import CurrentTenant

router = APIRouter(prefix="/mes", tags=["mes"])


class ReorderIn(BaseModel):
    step_ids: list[uuid.UUID]


@router.post("/route/{rid}/reorder")
def route_reorder(
    session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID, body: ReorderIn
) -> Any:
    """Renumber a draft route's steps (10, 20, 30, ...) in the given order."""
    e = require_entity(ctx, "route_step", "write")
    return {"data": reorder_steps(session, ctx.id, rid, body.step_ids, ctx.user, e)}
