"""RBAC 接口模型：权限与角色的 CRUD 及用户权限输出。"""

import uuid

from sqlmodel import Field, SQLModel

from app.platform.rbac.models import PermissionBase, RoleBase


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(SQLModel):
    code: str | None = Field(default=None, max_length=100)
    scope: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=255)


class PermissionPublic(PermissionBase):
    id: uuid.UUID


class PermissionsPublic(SQLModel):
    data: list[PermissionPublic]
    count: int


class RoleCreate(RoleBase):
    permission_codes: list[str] = []


class RoleUpdate(SQLModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=255)


class RolePublic(RoleBase):
    id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    permissions: list[PermissionPublic] = []


class RolesPublic(SQLModel):
    data: list[RolePublic]
    count: int


class UserPermissionsPublic(SQLModel):
    user_id: uuid.UUID
    is_superuser: bool
    roles: list[str]
    permissions: list[str]


class PermissionCodes(SQLModel):
    codes: list[str]
