"""Low-level row helpers for MES services (system columns, update, insert)."""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES

Row = dict[str, Any]


def _sys(user: Any, at: datetime) -> Row:
    return {
        "created_at": at,
        "updated_at": at,
        "created_by": getattr(user, "id", None),
        "updated_by": getattr(user, "id", None),
    }


def _upd(
    s: Session, tid: uuid.UUID, code: str, rid: Any, user: Any = None, **vals: Any
) -> None:
    t = TABLES[code]
    vals.setdefault("updated_at", now())
    if user is not None:
        vals.setdefault("updated_by", getattr(user, "id", None))
    conn(s).execute(
        sa.update(t).where(t.c.tenant_id == tid, t.c.id == rid).values(**vals)
    )


def _ins(s: Session, tid: uuid.UUID, ent: str, user: Any, **vals: Any) -> uuid.UUID:
    rid = uuid.uuid4()
    conn(s).execute(
        sa.insert(TABLES[ent]).values(
            id=rid, tenant_id=tid, **_sys(user, now()), **vals
        )
    )
    return rid
