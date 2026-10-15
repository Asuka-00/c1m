"""alembic 目标库防误迁移（env.py → check_db_target）。"""

import os
import subprocess
from pathlib import Path

import pytest

from app.core.migrate import check_db_target

URL = "postgresql+psycopg://u:p@localhost:5432/app"


def test_guard_rules() -> None:
    check_db_target(URL, {})  # 没设 POSTGRES_DB：不检查
    check_db_target(URL, {"POSTGRES_DB": "app"})  # 一致
    with pytest.raises(SystemExit) as ex:
        check_db_target(URL, {"POSTGRES_DB": "app_test_be_p2"})
    msg = str(ex.value)
    assert "'app_test_be_p2'" in msg and "'app'" in msg
    assert "ALEMBIC_ALLOW_DB_MISMATCH" in msg
    check_db_target(
        URL, {"POSTGRES_DB": "app_test_be_p2", "ALEMBIC_ALLOW_DB_MISMATCH": "1"}
    )
    with pytest.raises(SystemExit):
        check_db_target(URL, {"POSTGRES_DB": "x", "ALEMBIC_ALLOW_DB_MISMATCH": "true"})


def test_alembic_cli_refuses_mismatch() -> None:
    """真跑 alembic：库名不一致时在连库前退出，返回码非 0。"""
    from sqlalchemy.engine import make_url

    from app.core.config import settings

    url = make_url(settings.migration_database_url)
    env = {
        **os.environ,
        "MIGRATION_DATABASE_URL": url.render_as_string(hide_password=False),
        "POSTGRES_DB": f"{url.database}_not_this_one",
    }
    env.pop("ALEMBIC_ALLOW_DB_MISMATCH", None)
    r = subprocess.run(
        ["alembic", "current"],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert "refusing to run" in r.stderr
    assert f"target database = {url.database!r}" in r.stderr
