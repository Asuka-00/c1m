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
