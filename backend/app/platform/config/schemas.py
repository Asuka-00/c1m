import uuid
from typing import Any

from sqlmodel import SQLModel

from app.platform.config.models import ConfigValueType


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
