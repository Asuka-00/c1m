"""共享基础模型与工具函数。"""

from datetime import UTC, datetime

from sqlmodel import SQLModel


def get_datetime_utc() -> datetime:
    """返回当前 UTC 时间（带时区）。"""
    return datetime.now(UTC)


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
