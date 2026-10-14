"""光罩动作接口（P3-B4，docs p3-reticle-model v0.8.2 §3.2，D66–D69）。

``POST /mes/reticle/{id}/<动作>``，请求体 StrictBody（未知字段 422 unknown_field，D65 补充 4），
先查权限再校验请求体（D34）。权限：restore / life-reset / scrap 需 ``mes.reticle:override``，
其余写操作 ``mes.reticle:write``，履历 ``mes.reticle:read``。usage / incident 支持
``Idempotency-Key``（D57）：同 key 同内容以原状态码返回原记录，响应不带 duplicate。
时间 UTC Z（D45），定点数为十进制字符串（D50）。
"""

import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import Field, field_validator
from sqlmodel import Session

from app.core.deps import SessionDep
from app.core.schemas import StrictBody
from app.mes.common import idempotency as idem
from app.mes.common.guard import need, perm_body
from app.mes.common.numeric import six
from app.mes.reticle import service as svc
from app.platform.auth.deps import CurrentTenant

router = APIRouter(prefix="/mes/reticle", tags=["mes"])
READ, WRITE, OVERRIDE = "mes.reticle:read", "mes.reticle:write", "mes.reticle:override"
Text300 = Annotated[str, Field(min_length=1, max_length=300)]
Opt300 = Annotated[str | None, Field(default=None, max_length=300)]


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


class UnmountIn(StrictBody):
    unmounted_at: datetime | None = None
    comment: Opt300 = None


class IncidentIn(StrictBody):
    kind: Literal["collision", "drop", "other"]
    occurred_at: datetime | None = None
    equipment_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    description: Opt300 = None


class InspectionIn(StrictBody):
    kind: Literal["particle", "haze", "cd", "other"]
    result: Literal["pass", "fail"]
    defect_count: Annotated[int | None, Field(default=None, ge=0)] = None
    measured: dict[str, Any] | None = None
    equipment_id: uuid.UUID | None = None
    inspected_at: datetime | None = None
    disposition: Literal["none", "clean", "hold", "repair", "scrap"] | None = None
    comment: Opt300 = None


def _do(session: Session, fn: Callable[[], Any]) -> Any:
    out = fn()
    session.commit()
    return out


def _dump(b: Any) -> dict[str, Any] | None:
    return None if b is None else b.model_dump()


@router.post("/{rid}/hold")
def hold(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[ReasonIn, Depends(perm_body(WRITE, ReasonIn))],
) -> Any:
    """Manual hold (409 invalid_transition when already on_hold); unmounts if mounted."""
    return _do(
        session, lambda: svc.hold(session, ctx.id, rid, body.model_dump(), ctx.user)
    )


@router.post("/{rid}/release")
def release(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[
        CommentIn | None, Depends(perm_body(WRITE, CommentIn, optional=True))
    ],
) -> Any:
    """Release a hold; target follows the final hold_reason."""
    return _do(
        session, lambda: svc.release(session, ctx.id, rid, _dump(body), ctx.user)
    )


@router.post("/{rid}/restore")
def restore(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[ReasonIn, Depends(perm_body(OVERRIDE, ReasonIn))],
) -> Any:
    """pending_maintenance -> available (override; 409 life_limit_reached / still_mounted)."""
    return _do(
        session, lambda: svc.restore(session, ctx.id, rid, body.model_dump(), ctx.user)
    )


@router.post("/{rid}/life-reset")
def life_reset(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[ReasonIn, Depends(perm_body(OVERRIDE, ReasonIn))],
) -> Any:
    """Reset shot count (override; 409 still_mounted)."""
    return _do(
        session,
        lambda: svc.life_reset(session, ctx.id, rid, body.model_dump(), ctx.user),
    )


@router.post("/{rid}/scrap")
def scrap(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[ReasonIn, Depends(perm_body(OVERRIDE, ReasonIn))],
) -> Any:
    """Scrap (terminal, override); a mounted reticle is unmounted silently."""
    return _do(
        session, lambda: svc.scrap(session, ctx.id, rid, body.model_dump(), ctx.user)
    )


def _flow(action: str) -> Callable[..., Any]:
    def ep(
        session: SessionDep,
        ctx: CurrentTenant,
        rid: uuid.UUID,
        body: Annotated[
            CommentIn | None, Depends(perm_body(WRITE, CommentIn, optional=True))
        ],
    ) -> Any:
        return _do(
            session,
            lambda: svc.flow(session, ctx.id, rid, action, _dump(body), ctx.user),
        )

    ep.__doc__ = (
        f"Flow action {action.replace('_', '-')} (emits reticle.status_changed)."
    )
    ep.__name__ = action
    return ep


for _a in svc.FLOW:
    router.post(f"/{{rid}}/{_a.replace('_', '-')}")(_flow(_a))


@router.post("/{rid}/mount")
def mount(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[MountIn, Depends(perm_body(WRITE, MountIn))],
) -> Any:
    """Mount on an equipment (409 already_mounted / reticle_unavailable / slot_occupied)."""
    return _do(
        session, lambda: svc.mount(session, ctx.id, rid, body.model_dump(), ctx.user)
    )


@router.post("/{rid}/unmount")
def unmount(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[
        UnmountIn | None, Depends(perm_body(WRITE, UnmountIn, optional=True))
    ],
) -> Any:
    """Unmount (in_use -> available; other states only close the mount record)."""
    return _do(
        session, lambda: svc.unmount(session, ctx.id, rid, _dump(body) or {}, ctx.user)
    )


@router.post("/{rid}/usage")
def usage(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[UsageIn, Depends(perm_body(WRITE, UsageIn))],
    idempotency_key: Annotated[str | None, Header(alias=idem.HEADER)] = None,
) -> Any:
    """Manual shot report (delta > 0) / adjust (delta < 0, reason_id required)."""
    data = body.model_dump()
    return idem.run(
        session,
        ctx.id,
        ctx.user,
        "POST /mes/reticle/{rid}/usage",
        idempotency_key,
        {"rid": rid, **data},
        lambda: _do(session, lambda: svc.usage(session, ctx.id, rid, data, ctx.user)),
    )


@router.post("/{rid}/incident", status_code=201)
def incident(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[IncidentIn, Depends(perm_body(WRITE, IncidentIn))],
    idempotency_key: Annotated[str | None, Header(alias=idem.HEADER)] = None,
) -> Any:
    """Record an incident: non-scrapped -> on_hold(incident) + inspection required."""
    data = body.model_dump()
    return idem.run(
        session,
        ctx.id,
        ctx.user,
        "POST /mes/reticle/{rid}/incident",
        idempotency_key,
        {"rid": rid, **data},
        lambda: _do(
            session, lambda: svc.incident(session, ctx.id, rid, data, ctx.user)
        ),
        status_code=201,
    )


@router.post("/{rid}/inspection")
def inspection(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[InspectionIn, Depends(perm_body(WRITE, InspectionIn))],
    idempotency_key: Annotated[str | None, Header(alias=idem.HEADER)] = None,
) -> Any:
    """Inspection result: pass inspecting -> available; fail -> on_hold(inspection_failed).

    D71 补充：支持 D57 Idempotency-Key（重放返回原状态码与原响应，无 duplicate 字段）。
    """
    data = body.model_dump()
    return idem.run(
        session,
        ctx.id,
        ctx.user,
        "POST /mes/reticle/{rid}/inspection",
        idempotency_key,
        {"rid": rid, **data},
        lambda: _do(
            session, lambda: svc.inspection(session, ctx.id, rid, data, ctx.user)
        ),
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
