"""Demo dataset: seed is idempotent and remove deletes exactly the demo rows."""

import sqlalchemy as sa
from sqlmodel import Session

from app.core.db import engine
from app.core.spec.engine import TABLES
from app.mes.common.demo import DEMO, default_tenant
from app.mes.demo import remove, seed
from app.mes.planning.demo import STARTS


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
        if c
        not in (
            "audit_log",
            "code_rule_counter",
            "lot_history",
            "lot_recipe_run",
            "e10_history",
            "check_log",
            "lot_hold",
            "dc_result",
            "lot_genealogy",
        )
    )


def test_seed_and_remove() -> None:
    with Session(engine) as s:
        remove(s)
        before = _count(s)
        assert seed(s) == len(DEMO)
        assert seed(s) == 0
        started = (
            sum(  # lots + wafers (the assembly WO is quantity-tracked: no units)
                len(lots) + (0 if wo == "WO-DEMO-03" else sum(q for q, _ in lots))
                for wo, lots in STARTS
            )
            + 2  # split example: two child lots (one merged back)
            + 1  # future hold example
        )
        assert _count(s) == before + len(DEMO) + started  # + lots / wafers
        assert remove(s) >= len(DEMO)  # + started demo lots / wafers
        assert _count(s) == before
