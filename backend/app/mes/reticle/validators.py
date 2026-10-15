"""光罩主数据 CRUD 校验（P3-B4）：新建时 received_at 缺省取当前时间（D64）；有履历不可删（D72）。"""

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES, Entity
from app.core.spec.validate import validator

Row = dict[str, Any]


@validator("reticle:prefill")
def _received_at(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, old: Row | None
) -> None:
    if old is None and not row.get("received_at"):
        row["received_at"] = now()


# D72：5 张履历表 ON DELETE RESTRICT；有履历时删除返回 409 referenced + tables[]
HISTORY = (
    "reticle_incident",
    "reticle_mount_log",
    "reticle_usage",
    "reticle_inspection",
    "reticle_status_log",
)


@validator("reticle:delete")
def _referenced(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    used = []
    for code in HISTORY:
        t = TABLES[code]
        hit = (
            conn(s)
            .execute(
                sa.select(t.c.id)
                .where(t.c.tenant_id == tid, t.c.reticle_id == row["id"])
                .limit(1)
            )
            .first()
        )
        if hit:
            used.append(t.name)
    if used:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "referenced",
                "message": f"reticle {row.get('code')} has history; scrap it instead",
                "tables": used,
            },
        )
