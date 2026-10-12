import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.mes.common.query import find

Row = dict[str, Any]


def qtime_clock(
    s: Session, tid: uuid.UUID, lot_id: Any, step_id: Any, until: datetime | None
) -> datetime | None:
    """Start of a Q-Time clock: the lot's last move-out of `step_id`, inherited
    through genealogy (split parent / merge sources, before the event). An own
    move-out after the event supersedes it; otherwise the earliest (strictest)
    start wins."""
    h, g = TABLES["lot_history"], TABLES["lot_genealogy"]
    q = sa.select(sa.func.max(h.c.at)).where(
        h.c.tenant_id == tid,
        h.c.lot_id == lot_id,
        h.c.route_step_id == step_id,
        h.c.action == "move_out",
    )
    if until is not None:
        q = q.where(h.c.at <= until)
    own = conn(s).execute(q).scalar()
    gq = sa.select(g.c.parent_lot_id, g.c.at).where(
        g.c.tenant_id == tid, g.c.child_lot_id == lot_id
    )
    if until is not None:
        gq = gq.where(g.c.at <= until)
    cands = [own] if own else []
    for parent, at in conn(s).execute(gq).all():
        if own and own > at:
            continue
        c = qtime_clock(s, tid, parent, step_id, at)
        if c:
            cands.append(c)
    return min(cands) if cands else None


def qtime_status(
    s: Session, tid: uuid.UUID, lot: Row, step: Row, at: datetime
) -> list[Row]:
    """Q-Time rules ending at `step`: elapsed minutes since move-out of from_step."""
    out = []
    for r in find(s, tid, "qtime_rule", to_step_id=step["id"]):
        if r["product_id"] and r["product_id"] != lot["product_id"]:
            continue
        last = qtime_clock(s, tid, lot["id"], r["from_step_id"], None)
        if last is None:
            continue
        mins = (at - last).total_seconds() / 60
        out.append(
            {
                "rule": r,
                "since": last,
                "minutes": round(mins, 1),
                "too_early": bool(r["min_minutes"] and mins < r["min_minutes"]),
                "exceeded": bool(r["max_minutes"] and mins > r["max_minutes"]),
            }
        )
    return out
