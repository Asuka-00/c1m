import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, EmailStr, StringConstraints
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


# Shared properties
# login name (alternative to email); no '@' so it can't be confused with an email
USERNAME_RE = r"^[A-Za-z0-9_.-]{3,50}$"
# stored lower-case so the unique index is effectively case-insensitive
Username = Annotated[
    str, StringConstraints(pattern=USERNAME_RE), AfterValidator(str.lower)
]


class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    username: str | None = Field(default=None, unique=True, index=True, max_length=50)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    username: Username | None = Field(default=None, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    username: Username | None = Field(default=None, max_length=50)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    username: Username | None = Field(default=None, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


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


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    roles: list[Role] = Relationship(back_populates="users", link_model=UserRole)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None
    tid: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# ---------- RBAC ----------
class PermissionBase(SQLModel):
    code: str = Field(unique=True, index=True, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    # "platform" (global roles) or "tenant" (usable in tenant-scoped roles)
    scope: str = Field(default="platform", max_length=20)


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(SQLModel):
    code: str | None = Field(default=None, max_length=100)
    scope: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=255)


class Permission(PermissionBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    roles: list[Role] = Relationship(
        back_populates="permissions", link_model=RolePermission
    )


class PermissionPublic(PermissionBase):
    id: uuid.UUID


class PermissionsPublic(SQLModel):
    data: list[PermissionPublic]
    count: int


class RoleBase(SQLModel):
    name: str = Field(index=True, max_length=100)
    description: str | None = Field(default=None, max_length=255)


class RoleCreate(RoleBase):
    permission_codes: list[str] = []


class RoleUpdate(SQLModel):
    name: str | None = Field(default=None, max_length=100)
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


# ---------- Multi-tenancy ----------
class TenantBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(unique=True, index=True, min_length=2, max_length=63)


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


class Tenant(TenantBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    status: str = Field(default="active", max_length=20)
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    members: list[TenantMember] = Relationship(
        back_populates="tenant", passive_deletes="all"
    )


class TenantPublic(TenantBase):
    id: uuid.UUID
    status: str
    created_at: datetime | None = None


class TenantsPublic(SQLModel):
    data: list[TenantPublic]
    count: int


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


class PermissionCodes(SQLModel):
    codes: list[str]


# ---------- Backend-driven menus / routes ----------
class MenuBase(SQLModel):
    key: str = Field(unique=True, index=True, max_length=100)
    title: str = Field(max_length=100)
    path: str | None = Field(default=None, max_length=255)  # None => group node
    icon: str | None = Field(default=None, max_length=50)  # lucide icon name
    component: str | None = Field(
        default=None, max_length=100
    )  # frontend component key
    sort_order: int = 0
    permission: str | None = Field(default=None, max_length=100)  # required perm code
    hidden: bool = False


class MenuCreate(MenuBase):
    parent_id: uuid.UUID | None = None


class MenuUpdate(SQLModel):
    title: str | None = Field(default=None, max_length=100)
    path: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=50)
    component: str | None = Field(default=None, max_length=100)
    sort_order: int | None = None
    permission: str | None = Field(default=None, max_length=100)
    hidden: bool | None = None
    parent_id: uuid.UUID | None = None


class Menu(MenuBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    parent_id: uuid.UUID | None = Field(
        default=None, foreign_key="menu.id", ondelete="CASCADE", index=True
    )


class MenuPublic(MenuBase):
    id: uuid.UUID
    parent_id: uuid.UUID | None = None


class MenusPublic(SQLModel):
    data: list[MenuPublic]
    count: int


class MenuNode(SQLModel):
    key: str
    title: str
    path: str | None = None
    icon: str | None = None
    component: str | None = None
    permission: str | None = None
    children: list[MenuNode] = []


class MyMenus(SQLModel):
    menus: list[MenuNode]
    # known route paths the caller may NOT open (frontend shows 403 instead of 404)
    forbidden_paths: list[str] = []
    permissions: list[str]
    tenant_id: uuid.UUID | None = None
    is_superuser: bool = False


# ---------------- system configuration (platform-level) ----------------
class ConfigValueType(StrEnum):
    string = "string"
    text = "text"
    number = "number"
    boolean = "boolean"
    select = "select"
    color = "color"
    url = "url"
    image = "image"
    file = "file"
    json = "json"


class ConfigGroup(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    code: str = Field(unique=True, index=True, max_length=100)
    name: str = Field(max_length=255)
    name_key: str | None = Field(default=None, max_length=255)  # optional i18n key
    description: str | None = Field(default=None, max_length=1000)
    sort_order: int = 0
    items: list[ConfigItem] = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"order_by": "ConfigItem.sort_order"},
        cascade_delete=True,
    )


class ConfigItem(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("group_id", "code"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    group_id: uuid.UUID = Field(
        foreign_key="configgroup.id", ondelete="CASCADE", index=True
    )
    code: str = Field(max_length=100)
    name: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    value_type: ConfigValueType = Field(
        default=ConfigValueType.string,
        sa_column=Column(
            SAEnum(
                ConfigValueType, name="configvaluetype", native_enum=False, length=20
            ),
            nullable=False,
        ),
    )
    # values are stored JSON-encoded so every type round-trips (str, number, bool, object)
    value: Any | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    default_value: Any | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    options: list[dict[str, str]] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    validation: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    is_public: bool = False
    # tenants may override this item (TenantConfigValue); else platform-only
    tenant_overridable: bool = False
    sort_order: int = 0
    group: ConfigGroup | None = Relationship(back_populates="items")


class TenantConfigValue(SQLModel, table=True):
    """Per-tenant override of a ConfigItem (tenant-scoped table, RLS-protected)."""

    __table_args__ = (UniqueConstraint("tenant_id", "item_id"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID = Field(
        foreign_key="tenant.id", nullable=False, ondelete="CASCADE", index=True
    )
    item_id: uuid.UUID = Field(
        foreign_key="configitem.id", ondelete="CASCADE", index=True
    )
    value: Any | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    updated_at: datetime | None = Field(default_factory=get_datetime_utc)


class UploadedFile(SQLModel, table=True):
    """Metadata of an uploaded file. tenant_id NULL = platform-owned.
    Bytes live on disk under settings.UPLOAD_DIR/<id><ext>; served publicly by id
    (branding images must load on the sign-in page)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID | None = Field(
        default=None, foreign_key="tenant.id", ondelete="CASCADE", index=True
    )
    uploaded_by: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    filename: str = Field(max_length=255)
    stored_name: str = Field(max_length=64)
    content_type: str = Field(max_length=100)
    size: int
    created_at: datetime | None = Field(default_factory=get_datetime_utc)


class ConfigItemPublic(SQLModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    value_type: ConfigValueType
    value: Any | None = None
    default_value: Any | None = None
    options: list[dict[str, str]] | None = None
    validation: dict[str, Any] | None = None
    is_public: bool
    tenant_overridable: bool
    sort_order: int
    # tenant view only: platform value it inherits, and whether it is overridden
    platform_value: Any | None = None
    overridden: bool = False


class ConfigGroupPublic(SQLModel):
    id: uuid.UUID
    code: str
    name: str
    name_key: str | None = None
    description: str | None = None
    sort_order: int
    items: list[ConfigItemPublic]


class ConfigGroupsPublic(SQLModel):
    data: list[ConfigGroupPublic]
    count: int


class ConfigGroupUpdate(SQLModel):
    """Bulk update: item code -> new value (null resets to the default)."""

    values: dict[str, Any]


class FileUploadPublic(SQLModel):
    id: uuid.UUID
    url: str
    filename: str
    content_type: str
    size: int
    tenant_id: uuid.UUID | None = None


# MES master-data tables (generated from app.mes specs) share this metadata
import app.mes.specs  # noqa: E402, F401
import app.mes.validators  # noqa: E402, F401
