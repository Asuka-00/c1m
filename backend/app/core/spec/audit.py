import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import SYSTEM_COLS, Row, conn, now
from app.core.spec.engine import (
    TABLES,
    Entity,
)
from app.core.spec.serialize import to_json


# ---------------- audit ----------------
def audit(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    action: str,
    row: Row,
    user: Any,
    changes: Row | None = None,
) -> None:
    if e.code == "audit_log":
        return
    code = row.get("code") or row.get(e.label_field) or row.get("id")
    if e.versioned:
        code = f"{code} v{row.get('version')}"
    conn(session).execute(
        sa.insert(TABLES["audit_log"]).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            entity_type=e.code,
            action=action,
            record_id=str(row.get("id")),
            record_code=str(to_json(code))[:200],
            changes={
                k: [to_json(a), to_json(b)] for k, (a, b) in (changes or {}).items()
            },
            user_email=getattr(user, "email", None),
            created_at=now(),
            created_by=getattr(user, "id", None),
        )
    )


def diff(old: Row | None, new: Row) -> Row:
    return {
        k: (None if old is None else old.get(k), v)
        for k, v in new.items()
        if k not in SYSTEM_COLS and k != "id" and (old is None or old.get(k) != v)
    }
