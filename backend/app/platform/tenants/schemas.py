"""租户接口模型：租户、成员、成员角色及“我的租户”。"""

import uuid

from pydantic import EmailStr
from sqlmodel import Field, SQLModel

from app.core.models import UtcDateTime
from app.core.schemas import StrictSQLModel
from app.platform.tenants.models import TenantBase
from app.platform.users.schemas import Username


class TenantCreate(TenantBase):
    slug: str = Field(
        min_length=2,
        max_length=63,
        schema_extra={"pattern": r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"},
    )


class TenantUpdate(StrictSQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(
        default=None, schema_extra={"pattern": r"^(active|suspended)$"}
    )


class TenantPublic(TenantBase):
    id: uuid.UUID
    status: str
    plan: str = "standard"
    expires_at: UtcDateTime | None = None
    created_at: UtcDateTime | None = None


class TenantsPublic(SQLModel):
    data: list[TenantPublic]
    count: int


class MemberAdd(StrictSQLModel):
    """按用户名（或邮箱）添加已有用户为成员。"""

    username: str = Field(min_length=1, max_length=255)
    roles: list[str] = ["member"]


class MemberCreate(StrictSQLModel):
    """租户管理员在租户内直接创建新用户（不能创建超级用户，不创建个人工作区）。"""

    username: Username = Field(max_length=50)
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    roles: list[str] = ["member"]
    is_active: bool = True


class MemberUserUpdate(StrictSQLModel):
    """租户管理员修改成员账号（显示名 / 邮箱 / 状态 / 重置密码）：仅限只属于本租户的用户。"""

    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserTenantRoles(StrictSQLModel):
    """用户在某租户的成员身份（平台创建 / 编辑用户时直接分配）。"""

    tenant_id: uuid.UUID
    tenant_name: str | None = None
    roles: list[str] = ["member"]


class UserTenantsUpdate(StrictSQLModel):
    items: list[UserTenantRoles]


class MemberRolesUpdate(StrictSQLModel):
    roles: list[str]


class MemberPublic(SQLModel):
    user_id: uuid.UUID
    username: str
    email: EmailStr | None = None
    full_name: str | None = None
    is_active: bool = True
    roles: list[str]
    # 用户只属于本租户（且非超级用户）：租户管理员可重置密码 / 修改账号
    sole_tenant: bool = False


class MembersPublic(SQLModel):
    data: list[MemberPublic]
    count: int


class MyTenantPublic(SQLModel):
    tenant: TenantPublic
    roles: list[str]
    permissions: list[str]


class MyTenantsPublic(SQLModel):
    data: list[MyTenantPublic]
    count: int


class OwnerAssign(StrictSQLModel):
    """平台指定租户 owner：按用户名（或邮箱）选择已有用户。"""

    username: str = Field(min_length=1, max_length=255)
