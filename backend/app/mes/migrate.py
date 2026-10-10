"""Helpers used by the MES alembic migrations (RLS + permissions)."""

from typing import Any

import sqlalchemy as sa

from app.rls import disable_tenant_rls_sql, enable_tenant_rls_sql


def enable_rls(op: Any, tables: list[str]) -> None:
    for t in tables:
        for stmt in enable_tenant_rls_sql(t):
            op.execute(stmt)


def disable_rls(op: Any, tables: list[str]) -> None:
    for t in tables:
        for stmt in disable_tenant_rls_sql(t):
            op.execute(stmt)


def add_permissions(op: Any, modules: list[str]) -> None:
    """mes.<module>:read/write (tenant scope) -> platform admin, every tenant's
    owner/admin; members get :read."""
    conn = op.get_bind()
    codes = [f"mes.{m}:{a}" for m in modules for a in ("read", "write")]
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


def remove_permissions(op: Any, modules: list[str]) -> None:
    codes = [f"mes.{m}:{a}" for m in modules for a in ("read", "write")]
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM permission WHERE code = ANY(:c)"), {"c": codes})
    conn.execute(
        sa.text("DELETE FROM menu WHERE key = ANY(:k)"),
        {"k": [f"mes-g-{m}" for m in modules]},
    )
