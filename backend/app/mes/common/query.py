"""MES 模块共享的租户范围轻量查询工具。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.core.spec.serialize import to_json

Row = dict[str, Any]


def jsonable(v: Any) -> Any:
    """把值转换为 JSON 可序列化形式（递归处理 dict / list）。"""
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return to_json(v)


# ---------------- tiny query helpers ----------------
def one(s: Session, tid: uuid.UUID, code: str, rid: Any) -> Row | None:
    """按 id 读取实体行（限定租户），不存在返回 None。"""
    if rid is None:
        return None
    t = TABLES[code]
    r = (
        conn(s)
        .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.id == rid))
        .mappings()
        .first()
    )
    return dict(r) if r else None


def find(
    s: Session, tid: uuid.UUID, code: str, order: str | None = None, **eq: Any
) -> list[Row]:
    """按等值条件查询实体行（限定租户）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        code: 实体编码。
        order: 排序列名。
        **eq: 列等值条件。
    """
    t = TABLES[code]
    stmt = sa.select(t).where(t.c.tenant_id == tid)
    for k, v in eq.items():
        stmt = stmt.where(t.c[k].is_(None) if v is None else t.c[k] == v)
    if order:
        stmt = stmt.order_by(t.c[order])
    return [dict(r) for r in conn(s).execute(stmt).mappings()]
