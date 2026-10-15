"""RBAC 数据模型：权限、角色（平台 / 租户）及用户-角色、成员-角色、角色-权限关联表。"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.platform.users.models import User


# ---------- RBAC link tables ----------
class UserRole(SQLModel, table=True):
    __tablename__ = "user_role"
    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )
    role_id: uuid.UUID = Field(
        foreign_key="role.id", primary_key=True, ondelete="CASCADE"
    )


class MemberRole(SQLModel, table=True):
    __tablename__ = "member_role"
    member_id: uuid.UUID = Field(
        foreign_key="tenant_member.id", primary_key=True, ondelete="CASCADE"
    )
    role_id: uuid.UUID = Field(
        foreign_key="role.id", primary_key=True, ondelete="CASCADE"
    )


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permission"
    role_id: uuid.UUID = Field(
        foreign_key="role.id", primary_key=True, ondelete="CASCADE"
    )
    permission_id: uuid.UUID = Field(
        foreign_key="permission.id", primary_key=True, ondelete="CASCADE"
    )


# ---------- RBAC ----------
class PermissionBase(SQLModel):
    code: str = Field(unique=True, index=True, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    # "platform"（全局角色）或 "tenant"（可用于租户角色）
    scope: str = Field(default="platform", max_length=20)
    # 显示名称（为空时前端显示编码 / 描述）
    name: str | None = Field(default=None, max_length=100)
    # 类型：MENU（页面访问权限，挂在菜单上）/ BUTTON（页面内操作）/ API
    type: str = Field(default="BUTTON", max_length=10)
    # 所属菜单（权限树中挂在该菜单节点下）；为空则归入"其他权限"
    menu_id: uuid.UUID | None = Field(
        default=None, foreign_key="menu.id", ondelete="SET NULL", index=True
    )
    sort_order: int = 0
    # active / disabled：停用的权限不再授予任何角色
    status: str = Field(default="active", max_length=20)


class Permission(PermissionBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    roles: list[Role] = Relationship(
        back_populates="permissions", link_model=RolePermission
    )


class RoleBase(SQLModel):
    # 角色编码（唯一标识，如 owner / admin）
    name: str = Field(index=True, max_length=100)
    # 角色名称（显示名）
    title: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    # active / disabled：停用的角色不再授予任何权限
    status: str = Field(default="active", max_length=20)


class Role(RoleBase, table=True):
    # (tenant_id, name) 唯一；tenant_id 为空即平台角色（NULLS NOT DISTINCT）
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "name",
            name="uq_role_tenant_name",
            postgresql_nulls_not_distinct=True,
        ),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    updated_at: datetime | None = None
    updated_by: str | None = Field(default=None, max_length=255)
    tenant_id: uuid.UUID | None = Field(
        default=None, foreign_key="tenant.id", ondelete="CASCADE", index=True
    )
    permissions: list[Permission] = Relationship(
        back_populates="roles", link_model=RolePermission
    )
    users: list[User] = Relationship(back_populates="roles", link_model=UserRole)
