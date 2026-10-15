"""设备报警接口（P2-B9）。权限 mes.alarm:read / mes.alarm:write；先查权限再校验请求体
（D34）；严格请求体，传 ``source`` 422（D30）。时间输出 UTC Z（D45，经 serialize/iso_utc）。

模拟器兼容：``set_at`` / ``cleared_at`` 也接受字段名 ``occurred_at``。
"""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.core.deps import SessionDep
from app.core.pagination import ListParamsDep
from app.core.spec.qdates import check_range, datetime_query, parse_datetime
from app.mes.common.guard import need, perm_body
from app.mes.execution import alarm as svc
from app.platform.auth.deps import CurrentTenant

router = APIRouter(prefix="/mes/eqp", tags=["mes"])
READ, WRITE = "mes.alarm:read", "mes.alarm:write"


class AlarmSetIn(BaseModel):
    """人工登记报警（严格载荷）。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    alid: str = Field(min_length=1, max_length=32)
    alarm_text: str | None = Field(default=None, max_length=300)
    alcd_raw: int | None = Field(default=None, ge=0, le=255)
    set_at: datetime | None = Field(
        default=None, validation_alias=AliasChoices("set_at", "occurred_at")
    )
    lot_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    raw: dict[str, Any] | None = None
    comment: str | None = Field(default=None, max_length=300)
    external_event_id: str | None = Field(default=None, max_length=128)

    @field_validator("raw")
    @classmethod
    def _raw_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and len(json.dumps(v, default=str)) > svc.RAW_MAX:
            raise ValueError(f"raw: at most {svc.RAW_MAX} bytes of JSON")
        return v


class AlarmClearIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    cleared_at: datetime | None = Field(
        default=None, validation_alias=AliasChoices("cleared_at", "occurred_at")
    )
    comment: str | None = Field(default=None, max_length=300)
    external_event_id: str | None = Field(default=None, max_length=128)


@router.post("/{eq_id}/alarms")
def alarm_set(
    session: SessionDep,
    ctx: CurrentTenant,
    eq_id: uuid.UUID,
    body: Annotated[AlarmSetIn, Depends(perm_body(WRITE, AlarmSetIn))],
) -> Any:
    """Register an alarm (manual): links in-process lots and runs the alarm code
    action (hold lots / equipment state). Re-reporting an active ALID or the same
    external_event_id returns the existing record with duplicate=true (200)."""
    return svc.set_alarm(session, ctx.id, eq_id, body.model_dump(), ctx.user)


class AlarmClearByAlidIn(AlarmClearIn):
    equipment_id: uuid.UUID
    alid: str = Field(min_length=1, max_length=32)


@router.post("/alarms/clear")
def alarm_clear_by_alid(
    session: SessionDep,
    ctx: CurrentTenant,
    body: Annotated[AlarmClearByAlidIn, Depends(perm_body(WRITE, AlarmClearByAlidIn))],
) -> Any:
    """Clear the active alarm of (equipment_id, alid), as EAP reports it. No active
    alarm: 200 with data=null and cleared=false (D55)."""
    d = body.model_dump()
    return svc.clear_by_alid(
        session, ctx.id, d.pop("equipment_id"), d.pop("alid"), d, ctx.user
    )


@router.post("/alarms/{alarm_id}/clear")
def alarm_clear(
    session: SessionDep,
    ctx: CurrentTenant,
    alarm_id: uuid.UUID,
    body: Annotated[
        AlarmClearIn | None, Depends(perm_body(WRITE, AlarmClearIn, optional=True))
    ],
) -> Any:
    """Clear an alarm; holds and E10 state are NOT restored automatically.
    Already cleared: 200 with cleared=false and nothing changed (D55)."""
    data = body.model_dump() if body else {}
    return svc.clear_alarm(session, ctx.id, alarm_id, data, ctx.user)


@router.get("/alarms")
def alarm_list(
    session: SessionDep,
    ctx: CurrentTenant,
    params: ListParamsDep,
    equipment_id: uuid.UUID | None = None,
    status: Literal["active", "cleared"] | None = None,
    alid: str | None = Query(None, max_length=32),
    unregistered: bool | None = None,
    lot_id: uuid.UUID | None = None,
    set_from: Annotated[str | None, datetime_query("from")] = None,
    set_to: Annotated[str | None, datetime_query("to")] = None,
) -> Any:
    """Alarm log, newest first (page_size <= 100); lot_id finds alarms linked to a
    lot; from/to filter set_at as [from, to)."""
    need(ctx, READ)
    sf = parse_datetime("from", set_from)
    st = parse_datetime("to", set_to)
    check_range("from", sf, st)
    return svc.list_alarms(
        session,
        ctx.id,
        offset=params.offset,
        limit=params.limit,
        equipment_id=equipment_id,
        status=status,
        alid=alid,
        unregistered=unregistered,
        lot_id=lot_id,
        set_from=sf,
        set_to=st,
    )


@router.get("/alarms/{alarm_id}")
def alarm_get(session: SessionDep, ctx: CurrentTenant, alarm_id: uuid.UUID) -> Any:
    """Alarm detail with linked lots, linkage results and the raw report."""
    need(ctx, READ)
    return svc.get_alarm(session, ctx.id, alarm_id)
