"""平台控制台数据模型：登录日志与平台操作日志（平台级，不受租户 RLS 约束）。"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.core.models import get_datetime_utc


class LoginLog(SQLModel, table=True):
    """登录日志：每次 /login/access-token 尝试（成功或失败）记录一行。"""

    __tablename__ = "login_log"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # 登录名（尝试登录时输入的用户名）
    username: str = Field(max_length=255, index=True)
    user_id: uuid.UUID | None = Field(default=None, index=True)
    success: bool = Field(default=False, index=True)
    reason: str | None = Field(default=None, max_length=100)
    ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=500)
    created_at: datetime | None = Field(default_factory=get_datetime_utc, index=True)


class PlatformAudit(SQLModel, table=True):
    """平台操作日志：超级用户在平台控制台的写操作、跨租户读取与"以租户身份进入"。"""

    __tablename__ = "platform_audit"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    actor_id: uuid.UUID | None = Field(default=None, index=True)
    actor_username: str = Field(max_length=255)
    action: str = Field(max_length=50, index=True)
    target_type: str = Field(max_length=50)
    target_id: str | None = Field(default=None, max_length=64)
    tenant_id: uuid.UUID | None = Field(default=None, index=True)
    detail: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime | None = Field(default_factory=get_datetime_utc, index=True)
