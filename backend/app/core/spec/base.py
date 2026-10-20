"""规格服务基础：实体查找、表与连接访问、时钟。"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.engine import (
    ENTITIES,
    TABLES,
    Entity,
)
from app.core.spec.errors import coded

Row = dict[str, Any]
Validator = Callable[[Session, uuid.UUID, Entity, Row, Row | None], None]
SYSTEM_COLS = {"created_at", "updated_at", "created_by", "updated_by"}


def get_entity(code: str, *, api: bool = True) -> Entity:
    """按编码获取实体规格。

    Args:
        code: 实体编码。
        api: 为 True 时拒绝内部实体（不对外暴露）。

    Raises:
        HTTPException: 实体不存在（404）。
    """
    e = ENTITIES.get(code.replace("-", "_"))
    if not e or (api and e.internal):
        raise coded(404, ec.UNKNOWN_ENTITY, "Unknown entity")
    return e


def now() -> datetime:
    """当前 UTC 时间（统一时钟，便于测试替换）。"""
    return datetime.now(UTC)


def table(e: Entity) -> sa.Table:
    """实体对应的 SQLAlchemy 表。"""
    return TABLES[e.code]


def conn(session: Session) -> sa.Connection:
    """会话当前连接（沿用会话事务与租户上下文）。"""
    return session.connection()
