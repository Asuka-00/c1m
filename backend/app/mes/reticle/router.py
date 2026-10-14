"""光罩动作接口（P3-B4，docs p3-reticle-model v0.8.2 §3.2，D66–D69）。

``POST /mes/reticle/{id}/<动作>``，请求体 StrictBody（未知字段 422 unknown_field，D65 补充 4），
权限：restore / life-reset / scrap 需 ``mes.reticle:override``，其余写操作
``mes.reticle:write``，履历 ``mes.reticle:read``。

D80（含补充一、二）：14 个写接口一律必填 ``Idempotency-Key``。校验顺序按 D81：
权限 403 → 缺 key 422 ``missing``（loc ``["header","Idempotency-Key"]``）→ 请求体 422
（含补录时间 ``future_time``，D82-4）→ 幂等重放（同 key 同体按 D57 返回原状态码与原响应；
同 key 异体 422 ``idempotency_key_reused``，对象格式）→ 光罩 404 → 状态 / 业务 409。
时间 UTC Z（D45），定点数为十进制字符串（D50）。
"""

import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError
from sqlmodel import Session

from app.core.deps import SessionDep
from app.core.schemas import StrictBody
from app.core.spec.base import now
from app.mes.common import idempotency as idem
from app.mes.common.guard import need, perm_key_body
from app.mes.common.numeric import six
from app.mes.reticle import service as svc
from app.platform.auth.deps import CurrentTenant

router = APIRouter(prefix="/mes/reticle", tags=["mes"])
READ, WRITE, OVERRIDE = "mes.reticle:read", "mes.reticle:write", "mes.reticle:override"
Text300 = Annotated[str, Field(min_length=1, max_length=300)]
Opt300 = Annotated[str | None, Field(default=None, max_length=300)]


def event_at(v: datetime | None) -> datetime | None:
    """补录事件时间（D82-4）：必须带时区；晚于服务器当前时间 5 分钟以上 → value_error。"""
    if v is None:
        return None
    if v.tzinfo is None:
        raise PydanticCustomError("timezone_required", "timezone required")
    if v > now() + svc.CLOCK_SKEW:
        raise PydanticCustomError(
            "value_error",
            "more than 5 minutes in the future",
            {"reason": "future_time"},
        )
    return v


class ReasonIn(StrictBody):
    reason: Text300


class CommentIn(StrictBody):
    comment: Opt300 = None


class UsageIn(StrictBody):
    delta: Decimal
    reason_id: uuid.UUID | None = None
    note: Opt300 = None

    _six = field_validator("delta")(six)


class MountIn(StrictBody):
    equipment_id: uuid.UUID
    sub_unit_id: uuid.UUID | None = None
    slot_code: Annotated[str | None, Field(default=None, max_length=64)] = None
    mounted_at: datetime | None = None
    comment: Opt300 = None

    _at = field_validator("mounted_at")(event_at)


class UnmountIn(StrictBody):
    unmounted_at: datetime | None = None
    comment: Opt300 = None

    _at = field_validator("unmounted_at")(event_at)


class IncidentIn(StrictBody):
    kind: Literal["collision", "drop", "other"]
    occurred_at: datetime | None = None
    equipment_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    description: Opt300 = None

    _at = field_validator("occurred_at")(event_at)


class InspectionIn(StrictBody):
    kind: Literal["particle", "haze", "cd", "other"]
    result: Literal["pass", "fail"]
    defect_count: Annotated[int | None, Field(default=None, ge=0)] = None
    measured: dict[str, Any] | None = None
    equipment_id: uuid.UUID | None = None
    inspected_at: datetime | None = None
    disposition: Literal["none", "clean", "hold", "repair", "scrap"] | None = None
    comment: Opt300 = None

    _at = field_validator("inspected_at")(event_at)


def _write(
    session: Session,
    ctx: Any,
    rid: uuid.UUID,
    path: str,
    key: str | None,
    data: dict[str, Any] | None,
    fn: Callable[[], Any],
    status_code: int = 200,
) -> Any:
    """幂等执行（D57 / D80）：key 已由依赖保证非空；重放 / 换体判断先于 404 / 409（D81）。"""

    def go() -> Any:
        out = fn()
        session.commit()
        return out

    return idem.run(
        session,
        ctx.id,
        ctx.user,
        f"POST /mes/reticle/{{rid}}/{path}",
        key,
        {"rid": rid, **(data or {})},
        go,
        status_code=status_code,
    )


Key = Annotated[str | None, Header(alias=idem.HEADER)]


def _dump(b: Any) -> dict[str, Any] | None:
    return None if b is None else b.model_dump()


@router.post("/{rid}/hold")
def hold(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[ReasonIn, Depends(perm_key_body(WRITE, ReasonIn))],
    idempotency_key: Key = None,
) -> Any:
    """Manual hold (409 invalid_transition when already on_hold); unmounts if mounted."""
    d = body.model_dump()
    return _write(
        session,
        ctx,
        rid,
        "hold",
        idempotency_key,
        d,
        lambda: svc.hold(session, ctx.id, rid, d, ctx.user),
    )


@router.post("/{rid}/release")
def release(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[
        CommentIn | None, Depends(perm_key_body(WRITE, CommentIn, optional=True))
    ],
    idempotency_key: Key = None,
) -> Any:
    """Release a hold; target follows the final hold_reason."""
    d = _dump(body)
    return _write(
        session,
        ctx,
        rid,
        "release",
        idempotency_key,
        d,
        lambda: svc.release(session, ctx.id, rid, d, ctx.user),
    )


@router.post("/{rid}/restore")
def restore(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[ReasonIn, Depends(perm_key_body(OVERRIDE, ReasonIn))],
    idempotency_key: Key = None,
) -> Any:
    """pending_maintenance -> available (override; 409 life_limit_reached / still_mounted)."""
    d = body.model_dump()
    return _write(
        session,
        ctx,
        rid,
        "restore",
        idempotency_key,
        d,
        lambda: svc.restore(session, ctx.id, rid, d, ctx.user),
    )


@router.post("/{rid}/life-reset")
def life_reset(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[ReasonIn, Depends(perm_key_body(OVERRIDE, ReasonIn))],
    idempotency_key: Key = None,
) -> Any:
    """Reset shot count (override; 409 still_mounted)."""
    d = body.model_dump()
    return _write(
        session,
        ctx,
        rid,
        "life-reset",
        idempotency_key,
        d,
        lambda: svc.life_reset(session, ctx.id, rid, d, ctx.user),
    )


@router.post("/{rid}/scrap")
def scrap(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[ReasonIn, Depends(perm_key_body(OVERRIDE, ReasonIn))],
    idempotency_key: Key = None,
) -> Any:
    """Scrap (terminal, override); a mounted reticle is unmounted silently."""
    d = body.model_dump()
    return _write(
        session,
        ctx,
        rid,
        "scrap",
        idempotency_key,
        d,
        lambda: svc.scrap(session, ctx.id, rid, d, ctx.user),
    )


def _flow(action: str) -> Callable[..., Any]:
    path = action.replace("_", "-")

    def ep(
        session: SessionDep,
        ctx: CurrentTenant,
        rid: uuid.UUID,
        body: Annotated[
            CommentIn | None, Depends(perm_key_body(WRITE, CommentIn, optional=True))
        ],
        idempotency_key: Key = None,
    ) -> Any:
        d = _dump(body)
        return _write(
            session,
            ctx,
            rid,
            path,
            idempotency_key,
            d,
            lambda: svc.flow(session, ctx.id, rid, action, d, ctx.user),
        )

    ep.__doc__ = f"Flow action {path} (emits reticle.status_changed)."
    ep.__name__ = action
    return ep


for _a in svc.FLOW:
    router.post(f"/{{rid}}/{_a.replace('_', '-')}")(_flow(_a))


@router.post("/{rid}/mount")
def mount(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[MountIn, Depends(perm_key_body(WRITE, MountIn))],
    idempotency_key: Key = None,
) -> Any:
    """Mount on an equipment (409 already_mounted / reticle_unavailable / slot_occupied)."""
    d = body.model_dump()
    return _write(
        session,
        ctx,
        rid,
        "mount",
        idempotency_key,
        d,
        lambda: svc.mount(session, ctx.id, rid, d, ctx.user),
    )


@router.post("/{rid}/unmount")
def unmount(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[
        UnmountIn | None, Depends(perm_key_body(WRITE, UnmountIn, optional=True))
    ],
    idempotency_key: Key = None,
) -> Any:
    """Unmount (in_use -> available; other states only close the mount record)."""
    d = _dump(body)
    return _write(
        session,
        ctx,
        rid,
        "unmount",
        idempotency_key,
        d,
        lambda: svc.unmount(session, ctx.id, rid, d or {}, ctx.user),
    )


@router.post("/{rid}/usage")
def usage(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[UsageIn, Depends(perm_key_body(WRITE, UsageIn))],
    idempotency_key: Key = None,
) -> Any:
    """Manual shot report (delta > 0) / adjust (delta < 0, reason_id required)."""
    d = body.model_dump()
    return _write(
        session,
        ctx,
        rid,
        "usage",
        idempotency_key,
        d,
        lambda: svc.usage(session, ctx.id, rid, d, ctx.user),
    )


@router.post("/{rid}/incident", status_code=201)
def incident(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[IncidentIn, Depends(perm_key_body(WRITE, IncidentIn))],
    idempotency_key: Key = None,
) -> Any:
    """Record an incident: non-scrapped -> on_hold(incident) + inspection required."""
    d = body.model_dump()
    return _write(
        session,
        ctx,
        rid,
        "incident",
        idempotency_key,
        d,
        lambda: svc.incident(session, ctx.id, rid, d, ctx.user),
        status_code=201,
    )


@router.post("/{rid}/inspection")
def inspection(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[InspectionIn, Depends(perm_key_body(WRITE, InspectionIn))],
    idempotency_key: Key = None,
) -> Any:
    """Inspection result: pass inspecting -> available; fail -> on_hold(inspection_failed)."""
    d = body.model_dump()
    return _write(
        session,
        ctx,
        rid,
        "inspection",
        idempotency_key,
        d,
        lambda: svc.inspection(session, ctx.id, rid, d, ctx.user),
    )


@router.get("/{rid}/history")
def history(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Any:
    """Merged history (mounts, usage, inspections, incidents, status), newest first."""
    need(ctx, READ)
    return svc.history(session, ctx.id, rid, (page - 1) * page_size, page_size)
