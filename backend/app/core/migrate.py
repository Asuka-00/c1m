"""MES Alembic 迁移辅助：启用/关闭租户 RLS、增删权限并下发到默认角色。"""

from typing import Any

import sqlalchemy as sa

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


def add_permissions(
    op: Any, modules: list[str], extra: list[str] | None = None
) -> None:
    """新增 MES 权限并下发到默认角色。

    为每个模块生成 ``mes.<module>:read/write``（外加 ``extra`` 编码，租户作用域），
    授予平台 admin 与所有租户的 owner/admin；member 只获得 ``:read``。

    Args:
        op: Alembic ``op`` 对象。
        modules: 权限模块编码列表。
        extra: 额外权限 ``{编码: 描述}``。
    """
    conn = op.get_bind()
    codes = [f"mes.{m}:{a}" for m in modules for a in ("read", "write")]
    codes += extra or []
    for c in codes:
        conn.execute(
            sa.text(
                "INSERT INTO permission (id, code, description, scope) VALUES "
                "(gen_random_uuid(), :c, :d, 'tenant') ON CONFLICT (code) DO NOTHING"
            ),
            {"c": c, "d": f"MES {c}"},
        )
    conn.execute(
        sa.text(
            "INSERT INTO role_permission (role_id, permission_id) SELECT r.id, p.id "
            "FROM role r, permission p WHERE p.code = ANY(:c) AND ("
            "(r.tenant_id IS NULL AND r.name = 'admin') OR "
            "(r.tenant_id IS NOT NULL AND r.name IN ('owner', 'admin')) OR "
            "(r.tenant_id IS NOT NULL AND r.name = 'member' AND p.code LIKE '%\\:read'))"
            " ON CONFLICT DO NOTHING"
        ),
        {"c": codes},
    )


def remove_permissions(
    op: Any, modules: list[str], extra: list[str] | None = None
) -> None:
    """删除 :func:`add_permissions` 新增的权限（含角色关联）。"""
    codes = [f"mes.{m}:{a}" for m in modules for a in ("read", "write")]
    codes += extra or []
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM permission WHERE code = ANY(:c)"), {"c": codes})
    conn.execute(
        sa.text("DELETE FROM menu WHERE key = ANY(:k)"),
        {"k": [f"mes-g-{m}" for m in modules]},
    )
