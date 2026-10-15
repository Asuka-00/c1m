"""站内通知数据模型：通知、接收人（含每用户已读状态）、订阅配置（均为租户数据，受 RLS 保护）。"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.models import get_datetime_utc


class Notification(SQLModel, table=True):
    """一条通知（事件发生一次生成一条，按接收人展开到 :class:`NotificationRecipient`）。

    ``dedupe_key`` 在租户内唯一：同一事件（如同一次 Q-Time 超时）重复触发不会重复通知。
    标题 / 正文在前端按 ``event_type`` + ``params`` 本地化，``title`` / ``body`` 为英文兜底文本。
    """

    __tablename__ = "notification"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_notification_dedupe"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(
        foreign_key="tenant.id", ondelete="CASCADE", index=True
    )
    event_type: str = Field(max_length=64, index=True)
    severity: str = Field(default="info", max_length=16)
    title: str = Field(max_length=255)
    body: str | None = Field(default=None, max_length=1000)
    params: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    object_type: str | None = Field(default=None, max_length=64)
    object_id: str | None = Field(default=None, max_length=64)
    object_code: str | None = Field(default=None, max_length=200)
    link: str | None = Field(default=None, max_length=500)
    dedupe_key: str | None = Field(default=None, max_length=255)
    created_at: datetime | None = Field(default_factory=get_datetime_utc, index=True)


class NotificationRecipient(SQLModel, table=True):
    """通知的接收人与已读状态（``read_at`` 为空即未读）。"""

    __tablename__ = "notification_recipient"
    __table_args__ = (
        UniqueConstraint("notification_id", "user_id", name="uq_notification_user"),
        Index("ix_notification_recipient_user_read", "user_id", "read_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(
        foreign_key="tenant.id", ondelete="CASCADE", index=True
    )
    notification_id: uuid.UUID = Field(
        foreign_key="notification.id", ondelete="CASCADE", index=True
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE")
    read_at: datetime | None = None


class NotificationSubscription(SQLModel, table=True):
    """订阅配置：事件类型 → 租户角色 / 用户，按渠道投递，可启停。"""

    __tablename__ = "notification_subscription"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(
        foreign_key="tenant.id", ondelete="CASCADE", index=True
    )
    name: str = Field(max_length=200)
    event_type: str = Field(max_length=64, index=True)
    role_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    user_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    channels: list[str] = Field(
        default_factory=lambda: ["in_app"], sa_column=Column(JSON)
    )
    is_active: bool = True
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    updated_at: datetime | None = Field(default_factory=get_datetime_utc)
