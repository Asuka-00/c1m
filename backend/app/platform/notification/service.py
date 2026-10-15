"""站内通知服务：发送（订阅解析 + 去重 + 渠道投递）、我的通知查询与已读、订阅配置。

业务模块用法::

    from app.platform.notification.service import notify, register_event

    register_event("mes.oos", "OOS|超规|規格外", "critical", "lot")
    notify(session, tid, "mes.oos", title="...", params={...}, object_type="lot", ...)

``notify`` 在调用方事务内写入（不提交），与业务数据一起提交或回滚。
"""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, SQLModel, col, func, select

from app.core.models import get_datetime_utc, iso_utc
from app.core.pagination import ListParams, paginate
from app.platform.notification.channels import CHANNELS
from app.platform.notification.channels import register_channel as register_channel
from app.platform.notification.events import EVENT_TYPES, SEVERITIES
from app.platform.notification.events import register_event as register_event
from app.platform.notification.models import (
    Notification,
    NotificationRecipient,
    NotificationSubscription,
)
from app.platform.rbac.models import MemberRole
from app.platform.tenants.models import TenantMember

Row = dict[str, Any]


def recipients(
    session: Session, tid: uuid.UUID, event_type: str
) -> dict[str, set[uuid.UUID]]:
    """按有效订阅解析接收人：``{渠道: 用户 id 集合}``（仅当前租户成员）。"""
    subs = session.exec(
        select(NotificationSubscription).where(
            NotificationSubscription.tenant_id == tid,
            NotificationSubscription.event_type == event_type,
            col(NotificationSubscription.is_active).is_(True),
        )
    ).all()
    if not subs:
        return {}
    members = session.exec(
        select(TenantMember.id, TenantMember.user_id).where(
            TenantMember.tenant_id == tid
        )
    ).all()
    by_member = dict(members)
    users = set(by_member.values())
    roles: dict[str, set[uuid.UUID]] = {}
    for mid, rid in session.exec(
        select(MemberRole.member_id, MemberRole.role_id).where(
            col(MemberRole.member_id).in_(list(by_member))
        )
    ).all():
        roles.setdefault(str(rid), set()).add(by_member[mid])
    out: dict[str, set[uuid.UUID]] = {}
    for sub in subs:
        who: set[uuid.UUID] = set()
        for r in sub.role_ids or []:
            who |= roles.get(str(r), set())
        who |= {uuid.UUID(str(u)) for u in sub.user_ids or []} & users
        for ch in sub.channels or ["in_app"]:
            if ch in CHANNELS and channel_enabled(session, ch):
                out.setdefault(ch, set()).update(who)
    return out


def channel_enabled(session: Session, code: str) -> bool:
    """渠道是否启用：读取平台配置 ``notification.<code>_enabled``（未配置视为启用）。"""
    from app.platform.config.models import ConfigGroup, ConfigItem

    item = session.exec(
        select(ConfigItem)
        .join(ConfigGroup)
        .where(ConfigGroup.code == "notification", ConfigItem.code == f"{code}_enabled")
    ).first()
    return item is None or item.value is not False


def notify(
    session: Session,
    tid: uuid.UUID,
    event_type: str,
    *,
    title: str,
    body: str | None = None,
    params: Row | None = None,
    severity: str | None = None,
    object_type: str | None = None,
    object_id: Any = None,
    object_code: str | None = None,
    link: str | None = None,
    dedupe_key: str | None = None,
) -> uuid.UUID | None:
    """发送一条通知（调用方事务内，不提交）。

    无订阅接收人时不生成通知；``dedupe_key`` 已存在时视为重复，直接忽略。

    Args:
        session: 数据库会话（已设置租户 RLS 上下文）。
        tid: 租户 id。
        event_type: 已登记的事件类型编码。
        title: 英文兜底标题（前端按事件类型与 ``params`` 本地化）。
        body: 英文兜底正文。
        params: 本地化参数。
        severity: 严重度，缺省取事件类型默认值。
        object_type: 关联对象类型（缺省取事件类型的对象类型）。
        object_id: 关联对象 id。
        object_code: 关联对象编码（列表显示 / 搜索）。
        link: 前端跳转路径（如 ``/mes/lot-console?lot=<id>``）。
        dedupe_key: 去重键（租户内唯一）。

    Returns:
        新通知 id；重复或无接收人时为 None。

    Raises:
        ValueError: 事件类型未登记。
    """
    ev = EVENT_TYPES.get(event_type)
    if not ev:
        raise ValueError(f"unknown event type {event_type}")
    targets = recipients(session, tid, event_type)
    if not any(targets.values()):
        return None
    nid = uuid.uuid4()
    t = SQLModel.metadata.tables["notification"]
    got = (
        session.connection()
        .execute(
            insert(t)
            .values(
                id=nid,
                tenant_id=tid,
                event_type=event_type,
                severity=severity or ev.severity,
                title=title[:255],
                body=(body or None) and body[:1000],
                params=params,
                object_type=object_type or ev.object_type,
                object_id=object_id and str(object_id),
                object_code=object_code,
                link=link,
                dedupe_key=dedupe_key,
                created_at=get_datetime_utc(),
            )
            .on_conflict_do_nothing(constraint="uq_notification_dedupe")
            .returning(t.c.id)
        )
        .scalar()
    )
    if got is None:
        return None
    note = Notification(id=nid, tenant_id=tid, event_type=event_type, title=title)
    for code, users in targets.items():
        CHANNELS[code].deliver(session, note, users)
    return nid


def _row(n: Notification, read_at: datetime | None) -> Row:
    ev = EVENT_TYPES.get(n.event_type)
    return {
        "id": str(n.id),
        "event_type": n.event_type,
        "event_label": ev.label if ev else n.event_type,
        "severity": n.severity,
        "title": n.title,
        "body": n.body,
        "params": n.params or {},
        "object_type": n.object_type,
        "object_id": n.object_id,
        "object_code": n.object_code,
        "link": n.link,
        "created_at": n.created_at and iso_utc(n.created_at),
        "read_at": read_at and iso_utc(read_at),
        "is_read": read_at is not None,
    }


def _mine(tid: uuid.UUID, user_id: uuid.UUID) -> Any:
    return (
        select(Notification, NotificationRecipient.read_at)
        .join(
            NotificationRecipient,
            col(NotificationRecipient.notification_id) == col(Notification.id),
        )
        .where(
            NotificationRecipient.tenant_id == tid,
            NotificationRecipient.user_id == user_id,
        )
    )


def my_notifications(
    session: Session,
    tid: uuid.UUID,
    user_id: uuid.UUID,
    params: ListParams,
    event_type: str | None = None,
    severity: str | None = None,
    is_read: bool | None = None,
) -> tuple[list[Row], int]:
    """当前用户的通知（分页、搜索标题 / 对象编码，按类型 / 严重度 / 已读筛选）。"""
    stmt = _mine(tid, user_id)
    if event_type:
        stmt = stmt.where(Notification.event_type == event_type)
    if severity:
        stmt = stmt.where(Notification.severity == severity)
    if is_read is not None:
        rc = col(NotificationRecipient.read_at)
        stmt = stmt.where(rc.is_not(None) if is_read else rc.is_(None))
    rows, count = paginate(
        session,
        stmt,
        params,
        sortable={
            "created_at": col(Notification.created_at),
            "severity": col(Notification.severity),
            "event_type": col(Notification.event_type),
        },
        default=("created_at", "desc"),
        tiebreak=col(Notification.id),
        search=[col(Notification.title), col(Notification.object_code)],
    )
    return [_row(n, r) for n, r in rows], count


def summary(
    session: Session, tid: uuid.UUID, user_id: uuid.UUID, latest: int = 8
) -> Row:
    """铃铛数据：未读数与最近 ``latest`` 条。"""
    unread = session.exec(
        select(func.count())
        .select_from(NotificationRecipient)
        .where(
            NotificationRecipient.tenant_id == tid,
            NotificationRecipient.user_id == user_id,
            col(NotificationRecipient.read_at).is_(None),
        )
    ).one()
    rows = session.exec(
        _mine(tid, user_id)
        .order_by(col(Notification.created_at).desc(), col(Notification.id))
        .limit(latest)
    ).all()
    return {"unread": unread, "latest": [_row(n, r) for n, r in rows]}


def mark_read(
    session: Session,
    tid: uuid.UUID,
    user_id: uuid.UUID,
    ids: list[uuid.UUID] | None = None,
) -> int:
    """标记已读：``ids`` 为空时全部已读，返回更新条数。"""
    t = SQLModel.metadata.tables["notification_recipient"]
    q = sa.update(t).where(
        t.c.tenant_id == tid, t.c.user_id == user_id, t.c.read_at.is_(None)
    )
    if ids is not None:
        q = q.where(t.c.notification_id.in_(ids))
    n = session.connection().execute(q.values(read_at=get_datetime_utc())).rowcount
    session.commit()
    return int(n or 0)


def event_types() -> list[Row]:
    """已登记的事件类型列表。"""
    return [
        {
            "code": e.code,
            "label": e.label,
            "severity": e.severity,
            "object_type": e.object_type,
        }
        for e in sorted(EVENT_TYPES.values(), key=lambda x: x.code)
    ]


def channels() -> list[Row]:
    """已登记的渠道列表。"""
    return [{"code": c.code, "label": c.label} for c in CHANNELS.values()]


def validate_subscription(data: Row) -> list[tuple[str, str]]:
    """校验订阅配置，返回 ``[(字段, 错误)]``。"""
    errs = []
    if data.get("event_type") not in EVENT_TYPES:
        errs.append(("event_type", "event_type: unknown event type"))
    bad = [c for c in data.get("channels") or [] if c not in CHANNELS]
    if bad or not data.get("channels"):
        errs.append(("channels", f"channels: unknown or empty {bad}"))
    if not data.get("role_ids") and not data.get("user_ids"):
        errs.append(("role_ids", "role_ids: select at least one role or user"))
    return errs


__all__ = ["SEVERITIES", "notify", "register_channel", "register_event"]
