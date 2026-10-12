import uuid
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
    # "platform" (global roles) or "tenant" (usable in tenant-scoped roles)
    scope: str = Field(default="platform", max_length=20)


class Permission(PermissionBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    roles: list[Role] = Relationship(
        back_populates="permissions", link_model=RolePermission
    )


class RoleBase(SQLModel):
    name: str = Field(index=True, max_length=100)
    description: str | None = Field(default=None, max_length=255)


class Role(RoleBase, table=True):
    # (tenant_id, name) unique; NULL tenant_id = platform role (NULLS NOT DISTINCT)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "name",
            name="uq_role_tenant_name",
            postgresql_nulls_not_distinct=True,
        ),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID | None = Field(
        default=None, foreign_key="tenant.id", ondelete="CASCADE", index=True
    )
    permissions: list[Permission] = Relationship(
        back_populates="roles", link_model=RolePermission
    )
    users: list[User] = Relationship(back_populates="roles", link_model=UserRole)
