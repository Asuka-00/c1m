"""Route helpers: atomic step re-ordering (seq renumbering)."""

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
    # two passes so the (route, seq) unique constraint never collides
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
