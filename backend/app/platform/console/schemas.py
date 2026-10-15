"""平台控制台接口模型。"""

import uuid
from datetime import datetime
from typing import Any

from sqlmodel import Field, SQLModel


class PlatformTenant(SQLModel):
    """平台视角的租户：含套餐、到期时间、成员数与 owner。"""

    id: uuid.UUID
    name: str
    slug: str
    status: str
    plan: str
    expires_at: datetime | None = None
    created_at: datetime | None = None
    member_count: int = 0
    owners: list[str] = []


class PlatformTenants(SQLModel):
    data: list[PlatformTenant]
    count: int


class PlatformTenantCreate(SQLModel):
    """创建租户；``owner`` 按用户名（或邮箱）指定已有用户为 owner（为空则不设 owner）。"""

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(
        min_length=2, max_length=63, schema_extra={"pattern": r"^[a-z0-9][a-z0-9-]*$"}
    )
    plan: str = Field(
        default="standard", schema_extra={"pattern": r"^(trial|standard|enterprise)$"}
    )
    expires_at: datetime | None = None
    owner: str | None = Field(default=None, max_length=255)


class PlatformTenantUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(
        default=None, schema_extra={"pattern": r"^(active|suspended)$"}
    )
    plan: str | None = Field(
        default=None, schema_extra={"pattern": r"^(trial|standard|enterprise)$"}
    )
    expires_at: datetime | None = None


class LoginLogPublic(SQLModel):
    id: uuid.UUID
    username: str
    user_id: uuid.UUID | None = None
    success: bool
    reason: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    created_at: datetime | None = None


class LoginLogsPublic(SQLModel):
    data: list[LoginLogPublic]
    count: int


class PlatformAuditPublic(SQLModel):
    id: uuid.UUID
    actor_username: str
    action: str
    target_type: str
    target_id: str | None = None
    tenant_id: uuid.UUID | None = None
    detail: dict[str, Any] | None = None
    created_at: datetime | None = None


class PlatformAuditsPublic(SQLModel):
    data: list[PlatformAuditPublic]
    count: int


class CrossTenantAudit(SQLModel):
    """跨租户业务审计行（来自各租户的 audit_log）。"""

    id: str
    tenant_id: str
    tenant_name: str
    entity_type: str | None = None
    action: str | None = None
    record_code: str | None = None
    username: str | None = None
    changes: Any = None
    created_at: datetime | None = None


class CrossTenantAudits(SQLModel):
    data: list[CrossTenantAudit]
    count: int


class ChannelPublic(SQLModel):
    code: str
    label: str
    enabled: bool


class ChannelsPublic(SQLModel):
    data: list[ChannelPublic]
    count: int


class ChannelUpdate(SQLModel):
    enabled: bool
