"""D65 补充 4：所有请求体模型的共同基类，多余字段一律 422 ``unknown_field``。"""

from pydantic import BaseModel, ConfigDict
from sqlmodel import SQLModel


class StrictBody(BaseModel):
    """请求体基类（pydantic）：``extra="forbid"``，多余字段 → extra_forbidden → unknown_field。"""

    model_config = ConfigDict(extra="forbid")


class StrictSQLModel(SQLModel):
    """请求体基类（SQLModel，非表模型）：同 :class:`StrictBody`。"""

    model_config = ConfigDict(extra="forbid")  # type: ignore[assignment]


class NoBody(StrictBody):
    """动作接口不接受任何字段：不带请求体或 ``{}`` 放行，带任何字段 422 unknown_field。"""
