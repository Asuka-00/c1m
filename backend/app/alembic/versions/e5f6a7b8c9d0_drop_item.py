"""Remove the Item feature: drop item table (+ its RLS policy), items:* permissions
(role_permission links cascade / are cleaned) and the items menu.

The generic RLS infrastructure (app.current_tenant, app_user, app/rls.py) stays.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-10 17:50:00

"""
import sqlalchemy as sa
from alembic import op

from app.rls import disable_tenant_rls_sql, enable_tenant_rls_sql

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

ITEM_PERMS = {
    "items:read": "Read own items in the tenant",
    "items:write": "Create/update own items in the tenant",
    "items:delete": "Delete own items in the tenant",
    "items:read_all": "Read all items in the tenant",
}


def upgrade():
    conn = op.get_bind()
    for stmt in disable_tenant_rls_sql("item"):
        op.execute(stmt)
    op.drop_index(op.f("ix_item_tenant_id"), table_name="item")
    op.drop_table("item")
    codes = list(ITEM_PERMS)
    conn.execute(sa.text(
        "DELETE FROM role_permission WHERE permission_id IN "
        "(SELECT id FROM permission WHERE code = ANY(:c))"), {"c": codes})
    conn.execute(sa.text("DELETE FROM permission WHERE code = ANY(:c)"), {"c": codes})
    conn.execute(sa.text("UPDATE menu SET parent_id = NULL WHERE parent_id IN (SELECT id FROM menu WHERE key='items')"))
    conn.execute(sa.text("DELETE FROM menu WHERE key = 'items'"))


def downgrade():
    conn = op.get_bind()
    op.create_table(
        "item",
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_item_tenant_id"), "item", ["tenant_id"])
    for stmt in enable_tenant_rls_sql("item"):
        op.execute(stmt)
    for code, desc in ITEM_PERMS.items():
        conn.execute(sa.text(
            "INSERT INTO permission (id, code, description, scope) "
            "VALUES (gen_random_uuid(), :c, :d, 'tenant') ON CONFLICT (code) DO NOTHING"),
            {"c": code, "d": desc})
    # grant back to tenant owner/admin (all), member (own items) and platform admin
    grants = {"owner": list(ITEM_PERMS), "admin": list(ITEM_PERMS),
              "member": ["items:read", "items:write", "items:delete"]}
    for role, codes in grants.items():
        conn.execute(sa.text(
            "INSERT INTO role_permission (role_id, permission_id) "
            "SELECT r.id, p.id FROM role r, permission p WHERE r.name = :r AND p.code = ANY(:c) "
            "AND (r.tenant_id IS NOT NULL OR r.name = 'admin') ON CONFLICT DO NOTHING"),
            {"r": role, "c": codes})
