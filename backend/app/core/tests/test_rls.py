"""RLS backstop, proven on a throw-away tenant table created with the same generic
helpers (app/rls.py) a real tenant table migration would use."""

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session

from app.core.db import admin_engine, engine
from app.core.rls import disable_tenant_rls_sql, enable_tenant_rls_sql
from app.core.tenant import set_tenant
from app.platform.tenants.service import create_personal_tenant
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.utils import random_email, random_lower_string, username_for

TABLE = "rls_probe"


@pytest.fixture(scope="module")
def probe_table(db: Session) -> Generator[str]:
    db.commit()  # end the shared session's txn: CREATE ... REFERENCES tenant needs a lock on tenant
    with admin_engine.begin() as c:  # owner creates it, like a migration
        c.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        c.execute(
            text(
                f"CREATE TABLE {TABLE} (id uuid PRIMARY KEY, title text NOT NULL, "
                "tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE)"
            )
        )
        for stmt in enable_tenant_rls_sql(TABLE):
            c.execute(text(stmt))
        # app_user normally gets this through ALTER DEFAULT PRIVILEGES; be explicit
        app_role = engine.url.username
        c.execute(
            text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO "{app_role}"')
        )
    yield TABLE
    db.commit()
    with admin_engine.begin() as c:
        for stmt in disable_tenant_rls_sql(TABLE):
            c.execute(text(stmt))
        c.execute(text(f"DROP TABLE {TABLE}"))


def _tenant(db: Session) -> uuid.UUID:
    u = crud.create_user(
        session=db,
        user_create=UserCreate(
            email=random_email(),
            username=username_for(random_email()),
            password=random_lower_string(),
        ),
        with_personal_tenant=False,
    )
    return create_personal_tenant(db, u).id


def test_app_connects_as_non_owner_without_bypassrls(probe_table: str) -> None:
    with engine.connect() as c:
        role = c.execute(
            text(
                "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        owner = c.execute(
            text("SELECT tableowner FROM pg_tables WHERE tablename=:t"),
            {"t": probe_table},
        ).scalar_one()
        rls = c.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=:t"
            ),
            {"t": probe_table},
        ).one()
    assert role.rolsuper is False and role.rolbypassrls is False
    assert role.rolname != owner
    assert tuple(rls) == (True, True)


def test_rls_enforced_without_app_filter(db: Session, probe_table: str) -> None:
    """Unfiltered SQL only sees the current tenant's rows; with no tenant set nothing
    is visible; foreign UPDATE/DELETE affect nothing; foreign INSERT is rejected."""
    ta, tb = _tenant(db), _tenant(db)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    ins = text(
        f"INSERT INTO {probe_table} (id, title, tenant_id) VALUES (:i, :t, :tid)"
    )
    with Session(engine) as s:
        set_tenant(s, ta)
        s.execute(ins, {"i": a, "t": "a", "tid": str(ta)})
        s.commit()
    with Session(engine) as s:
        set_tenant(s, tb)
        s.execute(ins, {"i": b, "t": "b", "tid": str(tb)})
        s.commit()

    with Session(engine) as s:
        assert (
            s.execute(text(f"SELECT count(*) FROM {probe_table}")).scalar_one() == 0
        )  # no tenant
        set_tenant(s, ta)
        ids = {
            str(r[0]) for r in s.execute(text(f"SELECT id FROM {probe_table}"))
        }  # NO WHERE
        assert ids == {a}
        assert (
            s.execute(
                text(f"UPDATE {probe_table} SET title='hacked' WHERE id=:i"), {"i": b}
            ).rowcount
            == 0
        )  # type: ignore[attr-defined]
        assert (
            s.execute(text(f"DELETE FROM {probe_table} WHERE id=:i"), {"i": b}).rowcount
            == 0
        )  # type: ignore[attr-defined]
        s.commit()
        # context survives commit (SET LOCAL re-applied on each new transaction)
        assert s.execute(text(f"SELECT count(*) FROM {probe_table}")).scalar_one() == 1
        with pytest.raises(DBAPIError, match="row-level security"):
            s.execute(ins, {"i": str(uuid.uuid4()), "t": "x", "tid": str(tb)})
        s.rollback()

    with Session(engine) as s:
        set_tenant(s, tb)
        assert (
            s.execute(
                text(f"SELECT title FROM {probe_table} WHERE id=:i"), {"i": b}
            ).scalar_one()
            == "b"
        )
