import uuid
from datetime import datetime

from pydantic import EmailStr
from sqlmodel import Field, SQLModel

from app.platform.tenants.models import TenantBase


class TenantCreate(TenantBase):
    slug: str = Field(
        min_length=2,
        max_length=63,
        schema_extra={"pattern": r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"},
    )


class TenantUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(
        default=None, schema_extra={"pattern": r"^(active|suspended)$"}
    )


class TenantPublic(TenantBase):
    id: uuid.UUID
    status: str
    created_at: datetime | None = None


class TenantsPublic(SQLModel):
    data: list[TenantPublic]
    count: int


class MemberAdd(SQLModel):
    email: EmailStr
    roles: list[str] = ["member"]


class MemberRolesUpdate(SQLModel):
    roles: list[str]


class MemberPublic(SQLModel):
    user_id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    roles: list[str]


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
