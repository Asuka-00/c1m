"""通知接口：我的通知（列表 / 铃铛摘要 / 已读）、事件类型与渠道、订阅配置 CRUD。

权限：我的通知仅需登录并属于当前租户；订阅配置需 ``notify:config``。
"""

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.core import error_codes as ec
from app.core.deps import SessionDep
from app.core.models import get_datetime_utc
from app.core.pagination import ListParamsDep, paginate
from app.core.spec.errors import coded, http_422
from app.platform.auth.deps import CurrentTenant
from app.platform.notification import service as svc
from app.platform.notification.models import NotificationSubscription
from app.platform.tenants.service import TenantContext

router = APIRouter(tags=["notifications"])


def _need(ctx: TenantContext, p: str) -> None:
    if not ctx.can(p):
        raise coded(403, ec.PERMISSION_DENIED, "Not enough permissions")


# ---------------- my notifications ----------------
@router.get("/notifications")
def list_notifications(
    session: SessionDep,
    ctx: CurrentTenant,
    params: ListParamsDep,
    event_type: str | None = None,
    severity: str | None = None,
    is_read: bool | None = None,
) -> Any:
    """Notifications of the current user (paged, searchable, filterable)."""
    rows, count = svc.my_notifications(
        session, ctx.id, ctx.user.id, params, event_type, severity, is_read
    )
    return {"data": rows, "count": count}


@router.get("/notifications/summary")
def notification_summary(session: SessionDep, ctx: CurrentTenant) -> Any:
    """Unread count and latest notifications (header bell)."""
    return svc.summary(session, ctx.id, ctx.user.id)


class ReadIn(BaseModel):
    ids: list[uuid.UUID] | None = Field(default=None, max_length=500)


@router.post("/notifications/read")
def notifications_read(session: SessionDep, ctx: CurrentTenant, body: ReadIn) -> Any:
    """Mark notifications read (all unread when ``ids`` is omitted)."""
    return {"updated": svc.mark_read(session, ctx.id, ctx.user.id, body.ids)}


@router.get("/notification-meta")
def notification_meta(_ctx: CurrentTenant) -> Any:
    """Registered event types, channels and severities."""
    return {
        "event_types": svc.event_types(),
        "channels": svc.channels(),
        "severities": list(svc.SEVERITIES),
    }


# ---------------- subscriptions ----------------
class SubscriptionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    event_type: str = Field(max_length=64)
    role_ids: list[uuid.UUID] = Field(default_factory=list)
    user_ids: list[uuid.UUID] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=lambda: ["in_app"])
    is_active: bool = True


def _sub_out(s: NotificationSubscription) -> dict[str, Any]:
    return s.model_dump()


def _check(body: SubscriptionIn) -> dict[str, Any]:
    data = body.model_dump(mode="json")
    errs = svc.validate_subscription(data)
    if errs:
        raise http_422(errs)
    return data


@router.get("/notification-subscriptions")
def list_subscriptions(
    session: SessionDep,
    ctx: CurrentTenant,
    params: ListParamsDep,
    event_type: str | None = None,
    is_active: bool | None = None,
) -> Any:
    """Subscription configuration list."""
    _need(ctx, "notify:config")
    stmt = select(NotificationSubscription).where(
        NotificationSubscription.tenant_id == ctx.id
    )
    if event_type:
        stmt = stmt.where(NotificationSubscription.event_type == event_type)
    if is_active is not None:
        stmt = stmt.where(NotificationSubscription.is_active == is_active)
    rows, count = paginate(
        session,
        stmt,
        params,
        sortable={
            "name": col(NotificationSubscription.name),
            "event_type": col(NotificationSubscription.event_type),
            "created_at": col(NotificationSubscription.created_at),
        },
        default=("event_type", "asc"),
        tiebreak=col(NotificationSubscription.id),
        search=[col(NotificationSubscription.name)],
    )
    return {"data": [_sub_out(r) for r in rows], "count": count}


@router.post("/notification-subscriptions")
def create_subscription(
    session: SessionDep, ctx: CurrentTenant, body: SubscriptionIn
) -> Any:
    """Create a subscription."""
    _need(ctx, "notify:config")
    sub = NotificationSubscription(tenant_id=ctx.id, **_check(body))
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return _sub_out(sub)


def _get(session: Any, ctx: TenantContext, sid: uuid.UUID) -> NotificationSubscription:
    sub = session.get(NotificationSubscription, sid)
    if not sub or sub.tenant_id != ctx.id:
        raise coded(404, ec.SUBSCRIPTION_NOT_FOUND, "Subscription not found")
    return sub  # type: ignore[no-any-return]


@router.put("/notification-subscriptions/{sid}")
def update_subscription(
    session: SessionDep, ctx: CurrentTenant, sid: uuid.UUID, body: SubscriptionIn
) -> Any:
    """Update a subscription."""
    _need(ctx, "notify:config")
    sub = _get(session, ctx, sid)
    for k, v in _check(body).items():
        setattr(sub, k, v)
    sub.updated_at = get_datetime_utc()
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return _sub_out(sub)


@router.delete("/notification-subscriptions/{sid}")
def delete_subscription(session: SessionDep, ctx: CurrentTenant, sid: uuid.UUID) -> Any:
    """Delete a subscription."""
    _need(ctx, "notify:config")
    session.delete(_get(session, ctx, sid))
    session.commit()
    return {"ok": True}
