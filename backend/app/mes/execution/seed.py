"""执行模块的租户系统数据：系统原因码（D18）。"""

import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session

from app.core.spec.base import now
from app.core.spec.engine import TABLES
from app.core.tenant import set_tenant

#: 系统原因码：(reason_type, code, name)
SYSTEM_REASONS: tuple[tuple[str, str, str], ...] = (
    ("hold", "qtime_expired", "Q-Time 超时"),
    ("hold", "equipment_alarm", "设备报警"),  # P2-B9
)


def seed_system_reasons(session: Session, tenant_id: uuid.UUID) -> None:
    """为租户补建系统原因码（已存在则跳过，可重复执行）。"""
    prev: Any = session.info.get("tenant_id")
    set_tenant(session, tenant_id)
    try:
        t = TABLES["reason_code"]
        at = now()
        for rtype, code, name in SYSTEM_REASONS:
            session.connection().execute(
                insert(t)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    reason_type=rtype,
                    comment_required=False,
                    is_active=True,
                    attrs={"system": True},
                    created_at=at,
                    updated_at=at,
                )
                .on_conflict_do_nothing(constraint="uq_mes_reason_code_0")
            )
        session.flush()
    finally:
        set_tenant(session, prev)
