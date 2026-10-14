"""D83 / 0036：迁移给运行时角色授权（幂等；角色不存在 / 与迁移角色相同时跳过）。"""

import importlib.util
import logging
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.db import admin_engine, engine

VERSIONS = Path(__file__).resolve().parents[2] / "alembic/versions"


def _mig() -> ModuleType:
    path = next(VERSIONS.glob("0036_*.py"))
    spec = importlib.util.spec_from_file_location("m0036", path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ROLE = make_url(str(settings.DATABASE_URL)).username or ""


def _missing(c: Any) -> list[str]:
    return list(
        c.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n "
                "ON n.oid = c.relnamespace WHERE n.nspname = 'public' "
                "AND c.relkind IN ('r', 'p') AND c.relname <> 'alembic_version' "
                "AND NOT has_table_privilege(:r, c.oid, 'SELECT,INSERT,UPDATE,DELETE')"
            ),
            {"r": ROLE},
        ).scalars()
    )


def _apply(m: ModuleType, c: Any) -> None:
    role = m.runtime_role(c)
    assert role == ROLE
    db = c.execute(text("SELECT current_database()")).scalar()
    for stmt in m.grant_statements(role, db, m.migration_role(c)):
        c.execute(text(stmt))


def test_upgrade_head_already_granted() -> None:
    """conftest 只跑 upgrade head（不跑 setup_db_roles.py）：运行时角色已能读写。"""
    with admin_engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            "0036_d83_runtime_role_grants"
        )
        assert _missing(c) == []
    with engine.connect() as c:
        c.execute(text('SELECT count(*) FROM "user"')).scalar()


def test_grants_restore_and_idempotent() -> None:
    m = _mig()
    with admin_engine.connect() as c:
        tx = c.begin()
        try:
            c.execute(text(f'REVOKE ALL ON "user", mes_reticle FROM "{ROLE}"'))
            c.execute(
                text(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    f'REVOKE ALL ON TABLES FROM "{ROLE}"'
                )
            )
            assert {"user", "mes_reticle"} <= set(_missing(c))
            _apply(m, c)
            _apply(m, c)  # 重复执行安全
            assert _missing(c) == []
            acl = c.execute(
                text("SELECT defaclobjtype, defaclacl::text FROM pg_default_acl")
            ).all()
            kinds = {k for k, a in acl if f"{ROLE}=" in a}
            assert {"r", "S"} <= kinds  # 表 + 序列
            ver = c.execute(
                text(
                    "SELECT has_table_privilege(:r, 'alembic_version', 'SELECT'), "
                    "has_table_privilege(:r, 'alembic_version', 'INSERT')"
                ),
                {"r": ROLE},
            ).one()
            assert tuple(ver) == (True, False)
        finally:
            tx.rollback()


def test_missing_role_skipped_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """角色不存在：跳过并记 WARNING，不建角色。"""
    m = _mig()
    url = make_url(str(settings.DATABASE_URL)).set(username="d83_no_such_role")
    monkeypatch.setattr(
        settings, "DATABASE_URL", url.render_as_string(hide_password=False)
    )
    with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
        with admin_engine.connect() as c:
            assert m.runtime_role(c) is None
            assert not c.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = 'd83_no_such_role'")
            ).first()
    assert any(
        r.levelno == logging.WARNING and "does not exist" in r.getMessage()
        for r in caplog.records
    )


def test_same_role_as_migration_skipped(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    m = _mig()
    with admin_engine.connect() as c:
        me = c.execute(text("SELECT current_user")).scalar()
        url = make_url(str(settings.DATABASE_URL)).set(username=me)
        monkeypatch.setattr(
            settings, "DATABASE_URL", url.render_as_string(hide_password=False)
        )
        with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
            assert m.runtime_role(c) is None
    assert any("skip grants" in r.getMessage() for r in caplog.records)


def test_default_privileges_for_migration_role() -> None:
    """D83 补充一：默认权限写成 FOR ROLE <迁移角色>（migration_database_url 用户名）。"""
    m = _mig()
    owner = make_url(settings.migration_database_url).username
    assert owner
    with admin_engine.connect() as c:
        assert m.migration_role(c) == owner
        stmts = m.grant_statements(ROLE, "db", owner)
        dp = [x for x in stmts if x.startswith("ALTER DEFAULT PRIVILEGES")]
        assert len(dp) == 2
        assert all(f'FOR ROLE "{owner}" IN SCHEMA public' in x for x in dp)
        rows = c.execute(
            text(
                "SELECT defaclrole::regrole::text, defaclobjtype FROM pg_default_acl "
                "WHERE defaclacl::text LIKE :p"
            ),
            {"p": f"%{ROLE}=%"},
        ).all()
        assert {(r, k) for r, k in rows} >= {(owner, "r"), (owner, "S")}


def test_downgrade_keeps_table_grants() -> None:
    """downgrade 只撤默认权限，已有表 / 序列授权保留（事务内执行后回滚）。"""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    m = _mig()
    with admin_engine.connect() as c:
        ctx = MigrationContext.configure(c)
        with Operations.context(ctx):
            m.downgrade()
        assert _missing(c) == []
        left = c.execute(
            text("SELECT count(*) FROM pg_default_acl WHERE defaclacl::text LIKE :p"),
            {"p": f"%{ROLE}=%"},
        ).scalar()
        assert left == 0
        c.rollback()


def test_missing_role_warning_names_remedy(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    m = _mig()
    url = make_url(str(settings.DATABASE_URL)).set(username="d83_no_such_role")
    monkeypatch.setattr(
        settings, "DATABASE_URL", url.render_as_string(hide_password=False)
    )
    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        with admin_engine.connect() as c:
            assert m.runtime_role(c) is None
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "NOT be re-applied" in msg and "scripts/grant_runtime_role.py" in msg
    assert (Path(m.__file__).parents[3] / "scripts/grant_runtime_role.py").exists()
