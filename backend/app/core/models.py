"""共享基础模型与工具函数。"""

from datetime import UTC, datetime

from sqlmodel import SQLModel


def get_datetime_utc() -> datetime:
    """返回当前 UTC 时间（带时区）。"""
    return datetime.now(UTC)


# 通用消息
class Message(SQLModel):
    message: str
