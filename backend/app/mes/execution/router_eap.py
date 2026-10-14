"""EAP 事件入口路由（P2-B11）。权限 ``mes.eap:write`` 只看租户角色（服务账号），超级用户
不放行；先查权限再校验请求体（D34）。"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.deps import SessionDep
from app.mes.common.guard import raw_json
from app.mes.execution import eap as svc
from app.platform.auth.deps import CurrentTenant

router = APIRouter(prefix="/mes/eap", tags=["mes"])
WRITE = "mes.eap:write"
ENVELOPE = {"source", "external_event_id", "event_type", "equipment_id", "payload"}


class EventIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: Literal["eap", "simulator"]
    external_event_id: str = Field(min_length=1, max_length=128)
    event_type: svc.EventType
    equipment_id: uuid.UUID
    payload: dict[str, Any] | None = None


async def _body(request: Request, ctx: CurrentTenant) -> dict[str, Any]:
    if WRITE not in ctx.permissions:  # 服务账号专用：超级用户 / owner / admin 也 403
        raise HTTPException(status_code=403, detail="Not enough permissions")
    data = await raw_json(request, 1_048_576)
    try:
        m = EventIn.model_validate(data if data is not None else {})
    except ValidationError as ex:
        raise HTTPException(
            status_code=422,
            detail=[
                {"loc": ["body", *e["loc"]], "msg": e["msg"], "type": e["type"]}
                for e in ex.errors(include_url=False, include_context=False)
            ],
        ) from None
    flat = {k: v for k, v in (data or {}).items() if k not in ENVELOPE}
    nested = m.payload or {}
    both = sorted(set(flat) & set(nested))
    if both:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", k],
                    "msg": f"{k}: given both in payload and at top level",
                    "type": "duplicate_field",
                }
                for k in both
            ],
        )
    out = m.model_dump(include=ENVELOPE - {"payload"})
    out["payload"] = {**flat, **nested}
    return out


@router.post("/events")
def post_event(
    session: SessionDep,
    ctx: CurrentTenant,
    body: Annotated[dict[str, Any], Depends(_body)],
) -> Any:
    """EAP / simulator event intake (service accounts only). Idempotent on
    (source, external_event_id): a replay returns the first result with
    duplicate=true. Types: state, alarm_set, alarm_clear (by equipment_id + alid),
    tool_usage."""
    return svc.handle(session, ctx.id, body, ctx.user)
