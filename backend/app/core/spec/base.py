"""Spec service basics: entity lookup, table/connection access, clock."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.engine import (
    ENTITIES,
    TABLES,
    Entity,
)

Row = dict[str, Any]
Validator = Callable[[Session, uuid.UUID, Entity, Row, Row | None], None]
SYSTEM_COLS = {"created_at", "updated_at", "created_by", "updated_by"}


def get_entity(code: str, *, api: bool = True) -> Entity:
    e = ENTITIES.get(code.replace("-", "_"))
    if not e or (api and e.internal):
        raise HTTPException(status_code=404, detail="Unknown entity")
    return e


def now() -> datetime:
    return datetime.now(UTC)


def table(e: Entity) -> sa.Table:
    return TABLES[e.code]


def conn(session: Session) -> sa.Connection:
    return session.connection()
