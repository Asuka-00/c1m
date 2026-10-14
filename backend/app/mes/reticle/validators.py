"""光罩主数据 CRUD 校验（P3-B4）：新建时 received_at 缺省取当前时间（D64）。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.spec.base import now
from app.core.spec.engine import Entity
from app.core.spec.validate import validator

Row = dict[str, Any]


@validator("reticle:prefill")
def _received_at(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, old: Row | None
) -> None:
    if old is None and not row.get("received_at"):
        row["received_at"] = now()
