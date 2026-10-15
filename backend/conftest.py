import os
import subprocess
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path

# ---- Use a SEPARATE test database (never the dev DB) ----------------------
# Derived from the configured URLs by swapping the database name; override with
# TEST_DATABASE_NAME. Must be set before `app` is imported (settings are read once).
from sqlalchemy.engine import make_url

from app.core.config import Settings

_base = Settings()  # type: ignore[call-arg]
_test_db = os.environ.get("TEST_DATABASE_NAME", "").strip()
if not _test_db:  # 不再默认 app_test：多人共用机器时静默落到同一个库会互相覆盖
    raise SystemExit(
        "pytest: TEST_DATABASE_NAME is not set. Export it explicitly, e.g. "
        "TEST_DATABASE_NAME=app_test_<you> (the database is created and migrated "
        "automatically and wiped after the run)."
    )
# 共用机器上的应用库 / 联调库：测试跑完会清空，绝不能拿来当测试库
_PROTECTED = {"app", "app_it_be", "app_it_qa", "app_it_eap", "postgres"}
if _test_db in _PROTECTED or _test_db.startswith("app_it_"):
    raise SystemExit(
        f"pytest: TEST_DATABASE_NAME={_test_db!r} is an application / integration "
        "database; use a dedicated test database."
    )
_app_url = make_url(str(_base.DATABASE_URL)).set(database=_test_db)
_admin_url = make_url(_base.migration_database_url).set(database=_test_db)
os.environ["DATABASE_URL"] = _app_url.render_as_string(hide_password=False)
os.environ["MIGRATION_DATABASE_URL"] = _admin_url.render_as_string(hide_password=False)
# uploads go to a throw-away directory
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="app-test-uploads-")


def _prepare_test_database() -> None:
    from sqlalchemy import create_engine, text

    server = create_engine(
        _admin_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with server.connect() as c:
        if not c.execute(
            text("SELECT 1 FROM pg_database WHERE datname=:d"), {"d": _test_db}
        ).first():
            c.execute(text(f'CREATE DATABASE "{_test_db}"'))
    server.dispose()
    backend = Path(__file__).resolve().parent
    env = {**os.environ, "POSTGRES_DB": _test_db}
    for cmd in (
        ["alembic", "upgrade", "head"],
        [sys.executable, "scripts/setup_db_roles.py"],
    ):
        subprocess.run(cmd, cwd=backend, env=env, check=True, capture_output=True)


_prepare_test_database()
# Make sure the cached settings object picks up the test URLs
import app.core.config as _cfg

_cfg.settings = Settings()  # type: ignore[call-arg]

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, text

from app.bootstrap import init_db
from app.core.config import settings
from app.core.db import admin_engine, engine
from app.main import app
from app.testing.user import authentication_token_from_email
from app.testing.utils import get_superuser_token_headers


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session]:
    with Session(engine) as session:
        init_db(session)
        yield session
    # wipe the TEST database (as owner, so RLS does not hide rows)
    with admin_engine.begin() as c:
        c.execute(
            text('TRUNCATE member_role, tenant_member, user_role, "user" CASCADE')
        )
        c.execute(text("DELETE FROM role WHERE tenant_id IS NOT NULL"))
        c.execute(text("DELETE FROM tenant"))


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
