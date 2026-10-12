"""路线工具：原子化的工步重排（序号重编）。"""

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES, Entity
from app.core.spec.query import get_row
from app.core.spec.serialize import serialize
from app.core.spec.validate import check_editable

STEP = 10


def reorder_steps(
    session: Session,
    tid: uuid.UUID,
    route_id: uuid.UUID,
    ids: list[uuid.UUID],
    user: Any,
    e: Entity,
) -> list[dict[str, Any]]:
    """按给定顺序重排路线工步（仅 draft 路线）。

    Args:
        session: 数据库会话。
        tid: 租户 id。
        route_id: 路线 id。
        ids: 全部工步 id 的新顺序。
        user: 操作人。
        e: 工步实体规格。

    Returns:
        重排后的工步。

    Raises:
        HTTPException: 路线非 draft（409）或 id 集合不一致（422）。
    """
    route = get_row(session, ENTITIES["route"], tid, route_id)
    check_editable(session, tid, ENTITIES["route"], route)
    t = TABLES["route_step"]
    c = conn(session)
    current = {
        r["id"]: r["seq"]
        for r in c.execute(
            sa.select(t.c.id, t.c.seq).where(
                t.c.tenant_id == tid, t.c.route_id == route_id
            )
        ).mappings()
    }
    if set(ids) != set(current) or len(ids) != len(current):
        raise HTTPException(
            status_code=422,
            detail="step_ids must list every step of the route exactly once",
        )
    # 分两轮更新（先临时序号再正式序号），避免 (route, seq) 唯一约束冲突
    for i, sid in enumerate(ids):
        c.execute(sa.update(t).where(t.c.id == sid).values(seq=-(i + 1)))
    for i, sid in enumerate(ids):
        c.execute(
            sa.update(t)
            .where(t.c.id == sid)
            .values(seq=(i + 1) * STEP, updated_at=now())
        )
    audit(
        session,
        tid,
        ENTITIES["route"],
        "update",
        route,
        user,
        {
            "steps": (
                [current[i] for i in ids],
                [(n + 1) * STEP for n in range(len(ids))],
            )
        },
    )
    session.commit()
    rows = [
        dict(r)
        for r in conn(session)
        .execute(
            sa.select(t)
            .where(t.c.tenant_id == tid, t.c.route_id == route_id)
            .order_by(t.c.seq)
        )
        .mappings()
    ]
    return serialize(session, tid, e, rows)
