"""Shared base models/helpers."""

from datetime import UTC, datetime

from sqlmodel import SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


# Generic message
class Message(SQLModel):
    message: str
