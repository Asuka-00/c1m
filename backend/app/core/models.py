"""共享基础模型与工具函数。"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer
from sqlmodel import SQLModel


def get_datetime_utc() -> datetime:
    """返回当前 UTC 时间（带时区）。"""
    return datetime.now(UTC)


def iso_utc(v: datetime) -> str:
    """带时区的时间统一输出为 ISO 8601 UTC（``Z`` 结尾）；无时区的原样输出（bom.md §12）。"""
    if v.tzinfo is None:
        return v.isoformat()
    return v.astimezone(UTC).isoformat().replace("+00:00", "Z")


# 输出模型中的时间字段：JSON 输出统一为 UTC ``Z``；输入仍接受任意偏移。
UtcDateTime = Annotated[datetime, PlainSerializer(iso_utc, when_used="json")]


# 通用消息
class Message(SQLModel):
    message: str


def actor_name(user: object) -> str | None:
    """操作人标识：用户名（审计日志、更新人、批次履历等统一记录用户名）。

    Args:
        user: 用户对象（可为 None）。

    Returns:
        用户名；无用户名时回退邮箱；无用户时为 None。
    """
    return getattr(user, "username", None) or getattr(user, "email", None)
