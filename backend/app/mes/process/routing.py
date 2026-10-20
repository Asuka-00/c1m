"""路线工具：原子化的工步重排（序号重编）与画布布局保存。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES, Entity
from app.core.spec.errors import coded
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
    old_rows = list(
        c.execute(
            sa.select(t.c.id, t.c.seq, t.c.branch_to_seq).where(
                t.c.tenant_id == tid, t.c.route_id == route_id
            )
        ).mappings()
    )
    current = {r["id"]: r["seq"] for r in old_rows}
    if set(ids) != set(current) or len(ids) != len(current):
        raise coded(
            422,
            ec.ROUTE_STEP_IDS_INVALID,
            "step_ids must list every step of the route exactly once",
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
    # 分支目标按序号引用：随工步一起换成新序号
    new_seq = {current[sid]: (i + 1) * STEP for i, sid in enumerate(ids)}
    for r in old_rows:
        if r["branch_to_seq"] is not None and r["branch_to_seq"] in new_seq:
            c.execute(
                sa.update(t)
                .where(t.c.id == r["id"])
                .values(branch_to_seq=new_seq[r["branch_to_seq"]])
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


def save_layout(
    session: Session,
    tid: uuid.UUID,
    route_id: uuid.UUID,
    items: dict[uuid.UUID, dict[str, float] | None],
) -> int:
    """保存画布上节点的位置（仅 draft 路线；``None`` 清除该工步的已存位置）。

    Args:
        session: 数据库会话。
        tid: 租户 id。
        route_id: 路线 id。
        items: 工步 id -> ``{x, y, ax, ay, rx, ry}``（工步节点、子路线节点、返工路线节点的坐标）。

    Returns:
        更新的工步数。

    Raises:
        HTTPException: 路线非 draft（409）或含不属于该路线的工步（422）。
    """
    route = get_row(session, ENTITIES["route"], tid, route_id)
    check_editable(session, tid, ENTITIES["route"], route)
    t = TABLES["route_step"]
    c = conn(session)
    own = set(
        c.execute(
            sa.select(t.c.id).where(t.c.tenant_id == tid, t.c.route_id == route_id)
        ).scalars()
    )
    if not set(items) <= own:
        raise coded(
            422,
            ec.ROUTE_LAYOUT_INVALID,
            "The layout references steps outside this route",
        )
    for sid, pos in items.items():
        c.execute(
            sa.update(t)
            .where(t.c.id == sid)
            .values(layout=None if pos is None else dict(pos))
        )
    session.commit()
    return len(items)
