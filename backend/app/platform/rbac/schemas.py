"""RBAC 接口模型：权限与角色的 CRUD 及用户权限输出。"""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from app.platform.rbac.models import PermissionBase, RoleBase


class PermissionCreate(PermissionBase):
    pass


STATUS = r"^(active|disabled)$"
PERM_TYPE = r"^(MENU|BUTTON|API)$"


class PermissionUpdate(SQLModel):
    code: str | None = Field(default=None, max_length=100)
    scope: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=100)
    type: str | None = Field(default=None, schema_extra={"pattern": PERM_TYPE})
    menu_id: uuid.UUID | None = None
    sort_order: int | None = None
    status: str | None = Field(default=None, schema_extra={"pattern": STATUS})


class PermissionPublic(PermissionBase):
    id: uuid.UUID


class PermissionsPublic(SQLModel):
    data: list[PermissionPublic]
    count: int


class RoleCreate(RoleBase):
    permission_codes: list[str] = []


class RoleUpdate(SQLModel):
    name: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, schema_extra={"pattern": STATUS})


class RolePublic(RoleBase):
    id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None
    permissions: list[PermissionPublic] = []


class RolesPublic(SQLModel):
    data: list[RolePublic]
    count: int


class UserPermissionsPublic(SQLModel):
    user_id: uuid.UUID
    is_superuser: bool
    roles: list[str]
    permissions: list[str]


class RoleIds(SQLModel):
    role_ids: list[uuid.UUID]


class PermissionCodes(SQLModel):
    codes: list[str]
