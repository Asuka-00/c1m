"""EAP / 模拟器事件入口（P2-B11，D54-1 / D53-4 / D55）。

``POST /mes/eap/events``：只给服务账号（租户角色 ``eap_service``，权限 ``mes.eap:write``；
超级用户和 owner / admin 都没有）。请求体信封 ``{source, external_event_id, event_type,
equipment_id, payload}``，事件字段放 ``payload``，也可以平铺在信封里（两处重复的同名字段 422）。

- 幂等键 (tenant, source, external_event_id)：首次成功处理后写 ``mes_eap_event``，存响应；
  重放原样返回首次的 ``result``，``duplicate=true``，不再执行任何动作。处理失败（4xx）不入账，
  可修正后用同一事件号重发。下层表（alarm_log / tool_usage / 清除事件号）也带同一事件号，
  并发重放由它们的唯一约束兜底。
- ``state``：E10 迁移（迁移表照常校验），履历 ``source=equipment``；``event_at`` 超前 5 分钟
  422 ``time_in_future``。
- ``alarm_set`` / ``alarm_clear``：走 B9（D55 规则一致）；clear 按 (equipment_id, alid)，
  没有 active 报警 → 200、``cleared=false``。
- ``tool_usage``：走 B10 计数上报（``delta`` > 0；< 0 需 ``reason_id``）。
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.base import now
from app.core.spec.engine import ENTITIES
from app.core.spec.serialize import serialize
from app.mes.common.idempotency import body_hash, reused
from app.mes.common.query import find, one
from app.mes.common.rows import _ins
from app.mes.equipment import service as eqp_svc
from app.mes.execution import alarm as alarm_svc

Row = dict[str, Any]
EVT = "eap_event"
EventType = Literal["state", "alarm_set", "alarm_clear", "tool_usage"]


def six(v: Decimal) -> Decimal:
    """numeric(18,6)：最多 6 位小数（同 B10 手工接口）。"""
    if not v.is_finite():
        raise ValueError("must be a finite number")
    if v.as_tuple().exponent < -6:  # type: ignore[operator]
        raise ValueError("too_many_decimals (max 6)")
    if abs(v) >= Decimal(10) ** 12:
        raise ValueError("out of range")
    return v


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StateP(_P):
    """E10 状态变化。"""

    to_state_id: uuid.UUID
    reason_id: uuid.UUID | None = None
    event_at: datetime | None = None
    comment: str | None = Field(default=None, max_length=300)


class AlarmSetP(_P):
    """报警发生（字段同 B9 手工接口）。"""

    alid: str = Field(min_length=1, max_length=32)
    alarm_text: str | None = Field(default=None, max_length=300)
    alcd_raw: int | None = Field(default=None, ge=0, le=255)
    set_at: datetime | None = None
    lot_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    raw: dict[str, Any] | None = None
    comment: str | None = Field(default=None, max_length=300)


class AlarmClearP(_P):
    """报警清除，按 (equipment_id, alid)。"""

    alid: str = Field(min_length=1, max_length=32)
    cleared_at: datetime | None = None
    comment: str | None = Field(default=None, max_length=300)


class ToolUsageP(_P):
    """工具计数上报（同 B10）。"""

    tool_id: uuid.UUID
    delta: Decimal
    lot_id: uuid.UUID | None = None
    occurred_at: datetime | None = None
    reason_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=300)

    _six = field_validator("delta")(six)


PAYLOADS: dict[str, type[_P]] = {
    "state": StateP,
    "alarm_set": AlarmSetP,
    "alarm_clear": AlarmClearP,
    "tool_usage": ToolUsageP,
}


def _payload(event_type: str, merged: Row) -> Row:
    try:
        return PAYLOADS[event_type].model_validate(merged).model_dump()
    except ValidationError as ex:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "payload", *e["loc"]],
                    "msg": e["msg"],
                    "type": e["type"],
                }
                for e in ex.errors(include_url=False, include_context=False)
            ],
        ) from None


def _ledger(s: Session, tid: uuid.UUID, source: str, ext: str) -> Row | None:
    rows = find(s, tid, EVT, source=source, external_event_id=ext)
    return rows[0] if rows else None


def _out(s: Session, tid: uuid.UUID, row: Row, duplicate: bool) -> Row:
    data = serialize(s, tid, ENTITIES[EVT], [row])[0]
    result = data.pop("result", None)
    data.pop("payload", None)
    data.pop("request_hash", None)
    return {"data": data, "duplicate": duplicate, "result": result}


def handle(s: Session, tid: uuid.UUID, body: Row, user: Any) -> Row:
    """处理一条 EAP 事件，返回 ``{data: 台账行, duplicate, result: 下层接口响应}``。"""
    source, ext = body["source"], body["external_event_id"].strip()
    typ, eq_id = body["event_type"], body["equipment_id"]
    h = body_hash(
        {"event_type": typ, "equipment_id": eq_id, "payload": body["payload"]}
    )
    old = _ledger(s, tid, source, ext)
    if old:
        # D57：同一事件号内容不同 → 422 idempotency_key_reused，不写入
        if old.get("request_hash") != h:
            raise reused()
        s.commit()
        return _out(s, tid, old, True)
    if not one(s, tid, "equipment", eq_id):
        raise HTTPException(status_code=404, detail="equipment not found")
    p = _payload(typ, body["payload"])
    p["external_event_id"] = ext
    if typ == "state":
        alarm_svc._time(p.pop("event_at"), "event_at")
        p.pop("external_event_id")
        result = eqp_svc.e10_change(s, tid, eq_id, p, user, source="equipment")
    elif typ == "alarm_set":
        p["raw"] = p.get("raw") or {"payload": jsonable_encoder(body["payload"])}
        result = alarm_svc.set_alarm(s, tid, eq_id, p, user, source=source)
    elif typ == "alarm_clear":
        result = alarm_svc.clear_by_alid(
            s, tid, eq_id, p.pop("alid"), p, user, source=source
        )
    else:
        tool_id = p.pop("tool_id")
        p["equipment_id"] = eq_id
        result = eqp_svc.report_usage(s, tid, tool_id, p, user, source=source)
    enc = jsonable_encoder(result)
    try:
        with s.begin_nested():
            rid = _ins(
                s,
                tid,
                EVT,
                user,
                source=source,
                external_event_id=ext,
                event_type=typ,
                equipment_id=eq_id,
                payload=jsonable_encoder(body["payload"]),
                request_hash=h,
                result=enc,
                username=actor_name(user),
                received_at=now(),
            )
    except IntegrityError:
        s.rollback()
        dup = _ledger(s, tid, source, ext)
        if not dup:
            raise
        if dup.get("request_hash") != h:
            raise reused() from None
        return _out(s, tid, dup, True)
    s.commit()
    row = one(s, tid, EVT, rid)
    assert row
    return _out(s, tid, row, False)
