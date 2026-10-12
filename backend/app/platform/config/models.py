"""系统配置数据模型：配置值类型、配置分组、配置项（平台值）、租户覆盖值（受 RLS 保护）。"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, Relationship, SQLModel

from app.core.models import get_datetime_utc


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
    name_key: str | None = Field(default=None, max_length=255)  # 可选的 i18n key
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
    # 值以 JSON 编码存储，各类型（字符串、数字、布尔、对象）可无损往返
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
    # 租户可覆盖此项（TenantConfigValue）；否则仅平台级
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
