"""Alembic 迁移辅助：启用 / 关闭租户 RLS。"""

from typing import Any

from app.core.rls import disable_tenant_rls_sql, enable_tenant_rls_sql


def enable_rls(op: Any, tables: list[str]) -> None:
    """为租户表启用 RLS 策略（按 ``app.current_tenant`` 过滤）。

    Args:
        op: Alembic ``op`` 对象。
        tables: 表名列表。
    """
    for t in tables:
        for stmt in enable_tenant_rls_sql(t):
            op.execute(stmt)


def disable_rls(op: Any, tables: list[str]) -> None:
    """删除租户表的 RLS 策略（:func:`enable_rls` 的逆操作）。"""
    for t in tables:
        for stmt in disable_tenant_rls_sql(t):
            op.execute(stmt)


def check_db_target(url: str, env: dict[str, str] | None = None) -> None:
    """防误迁移：设置了环境变量 ``POSTGRES_DB`` 而实际迁移连接的库名不同 → 报错退出。

    配置读的是 ``MIGRATION_DATABASE_URL``（常来自 .env），只设 ``POSTGRES_DB`` 不会改变目标库，
    曾因此误迁移了 ``app``。确需不一致时设 ``ALEMBIC_ALLOW_DB_MISMATCH=1`` 跳过。
    """
    import os
    import sys

    from sqlalchemy.engine import make_url

    e = os.environ if env is None else env
    got = make_url(url).database
    sys.stderr.write(f"alembic: target database = {got!r}\n")
    want = (e.get("POSTGRES_DB") or "").strip()
    if not want or e.get("ALEMBIC_ALLOW_DB_MISMATCH") == "1":
        return
    if got != want:
        raise SystemExit(
            f"alembic: refusing to run: POSTGRES_DB={want!r} but the migration URL "
            f"targets database {got!r}. Set MIGRATION_DATABASE_URL to the intended "
            "database (POSTGRES_DB alone does not change it), or set "
            "ALEMBIC_ALLOW_DB_MISMATCH=1 to bypass."
        )
