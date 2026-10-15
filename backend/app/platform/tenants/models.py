"""租户数据模型：租户与成员关系。"""

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.core.models import get_datetime_utc
from app.platform.rbac.models import MemberRole, Role
from app.platform.users.models import User


# ---------- Multi-tenancy ----------
class TenantBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(unique=True, index=True, min_length=2, max_length=63)


class Tenant(TenantBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    status: str = Field(default="active", max_length=20)
    # 套餐（trial / standard / enterprise），由平台管理维护
    plan: str = Field(default="standard", max_length=20)
    # 到期时间（None 表示永久）；过期后非超级用户无法进入租户
    expires_at: datetime | None = None
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    members: list[TenantMember] = Relationship(
        back_populates="tenant", passive_deletes="all"
    )


class TenantMember(SQLModel, table=True):
    __tablename__ = "tenant_member"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_member"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(
        foreign_key="tenant.id", ondelete="CASCADE", index=True
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    tenant: Tenant = Relationship(back_populates="members")
    user: User = Relationship()
    roles: list[Role] = Relationship(link_model=MemberRole)
