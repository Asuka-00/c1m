"""Demo dataset: seed is idempotent and remove deletes exactly the demo rows."""

import sqlalchemy as sa
from sqlmodel import Session

from app.core.db import engine
from app.mes.core import TABLES
from app.mes.demo import DEMO, default_tenant, remove, seed


def _count(s: Session) -> int:
    tid = default_tenant(s)
    return sum(
        s.connection()
        .execute(
            sa.select(sa.func.count())
            .select_from(TABLES[c])
            .where(TABLES[c].c.tenant_id == tid)
        )
        .scalar_one()
        for c in TABLES
        if c not in ("audit_log", "code_rule_counter")
    )


def test_seed_and_remove() -> None:
    with Session(engine) as s:
        remove(s)
        before = _count(s)
        assert seed(s) == len(DEMO)
        assert seed(s) == 0
        assert _count(s) == before + len(DEMO)
        assert remove(s) == len(DEMO)
        assert _count(s) == before
