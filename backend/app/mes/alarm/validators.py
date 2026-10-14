"""报警码 CRUD 校验（D59）。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES, Entity
from app.core.spec.errors import MesError
from app.core.spec.validate import validator

Row = dict[str, Any]


def state_by_code(
    s: Session, tid: uuid.UUID, code: str | None
) -> dict[str, Any] | None:
    """按编码取 E10 状态行（D59 target_state）。"""
    if not code:
        return None
    t = TABLES["e10_state"]
    r = (
        conn(s)
        .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.code == code))
        .mappings()
        .first()
    )
    return dict(r) if r else None


@validator("alarm_code")
def _alarm_code(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    """action=set_state 必须给存在的 E10 状态编码；action=none 不能带 target_state。"""
    act, ts = row.get("action") or "none", (row.get("target_state") or "").strip()
    if act == "set_state":
        if not ts:
            raise MesError(
                [("target_state", "target_state: required when action=set_state")]
            )
        if not state_by_code(s, tid, ts):
            raise MesError([("target_state", f"target_state: unknown E10 state {ts}")])
    elif ts:
        raise MesError(
            [("target_state", "target_state: only allowed when action=set_state")]
        )
