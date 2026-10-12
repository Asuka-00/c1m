"""Multi-tenancy: tenant, tenant_member, member_role, tenant-scoped roles,
item.tenant_id (NOT NULL) and Postgres row level security on item.

Revision ID: c3d4e5f6a7b8
Revises: b7c1d2e3f4a5
Create Date: 2026-10-10 17:00:00

"""
import uuid

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b7c1d2e3f4a5"
branch_labels = None
depends_on = None

S = sqlmodel.sql.sqltypes.AutoString

NEW_TENANT_PERMS = {
    "tenant:manage": "Update/delete the tenant",
    "members:read": "List tenant members",
    "members:write": "Add/remove members and change their roles",
}
NEW_PLATFORM_PERMS = {
    "tenants:read": "Read any tenant (platform)",
    "tenants:write": "Manage any tenant (platform)",
}
ITEM_PERMS = ["items:read", "items:write", "items:delete", "items:read_all"]
TENANT_ROLES = {
    "owner": ("Tenant owner", list(NEW_TENANT_PERMS) + ITEM_PERMS),
    "admin": ("Tenant administrator", ["members:read", "members:write"] + ITEM_PERMS),
    "member": ("Tenant member", ["members:read", "items:read", "items:write", "items:delete"]),
}

# Policy: rows are visible / writable only when tenant_id matches the per-transaction
# setting app.current_tenant (missing setting -> NULL -> no rows).
RLS_EXPR = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade():
    conn = op.get_bind()
    op.create_table(
        "tenant",
        sa.Column("name", S(length=255), nullable=False),
        sa.Column("slug", S(length=63), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", S(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_slug"), "tenant", ["slug"], unique=True)
    op.create_table(
        "tenant_member",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_member"),
    )
    op.create_index(op.f("ix_tenant_member_tenant_id"), "tenant_member", ["tenant_id"])
    op.create_index(op.f("ix_tenant_member_user_id"), "tenant_member", ["user_id"])

    # roles become two-tier: tenant_id NULL = platform role
    op.add_column("role", sa.Column("tenant_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("role_tenant_id_fkey", "role", "tenant", ["tenant_id"], ["id"], ondelete="CASCADE")
    op.create_index(op.f("ix_role_tenant_id"), "role", ["tenant_id"])
    op.drop_index("ix_role_name", table_name="role")
    op.create_index(op.f("ix_role_name"), "role", ["name"], unique=False)
    op.create_unique_constraint(
        "uq_role_tenant_name", "role", ["tenant_id", "name"], postgresql_nulls_not_distinct=True
    )
    op.create_table(
        "member_role",
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["tenant_member.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("member_id", "role_id"),
    )

    # permissions: scope column + new codes
    op.add_column("permission", sa.Column("scope", S(length=20), nullable=False, server_default="platform"))
    op.alter_column("permission", "scope", server_default=None)
    for code, desc in {**NEW_TENANT_PERMS, **NEW_PLATFORM_PERMS}.items():
        conn.execute(
            sa.text("INSERT INTO permission (id, code, description, scope) VALUES (:i,:c,:d,:s) ON CONFLICT (code) DO NOTHING"),
            {"i": uuid.uuid4(), "c": code, "d": desc, "s": "tenant" if code in NEW_TENANT_PERMS else "platform"},
        )
    conn.execute(sa.text("UPDATE permission SET scope='tenant' WHERE code = ANY(:c)"), {"c": ITEM_PERMS + list(NEW_TENANT_PERMS)})
    # platform admin gets the new perms; platform 'user' loses item perms (now tenant-level)
    conn.execute(sa.text(
        "INSERT INTO role_permission (role_id, permission_id) SELECT r.id, p.id FROM role r, permission p "
        "WHERE r.name='admin' AND r.tenant_id IS NULL ON CONFLICT DO NOTHING"))
    conn.execute(sa.text(
        "DELETE FROM role_permission WHERE role_id IN (SELECT id FROM role WHERE name='user' AND tenant_id IS NULL) "
        "AND permission_id IN (SELECT id FROM permission WHERE code = ANY(:c))"), {"c": ITEM_PERMS})

    # default tenant + its roles; every existing user joins it
    tid = uuid.uuid4()
    conn.execute(sa.text("INSERT INTO tenant (id, name, slug, status, created_at) VALUES (:i, 'Default', 'default', 'active', now())"), {"i": tid})
    role_ids = {}
    for name, (desc, codes) in TENANT_ROLES.items():
        rid = role_ids[name] = uuid.uuid4()
        conn.execute(sa.text("INSERT INTO role (id, name, description, tenant_id) VALUES (:i,:n,:d,:t)"), {"i": rid, "n": name, "d": desc, "t": tid})
        conn.execute(sa.text("INSERT INTO role_permission (role_id, permission_id) SELECT :r, id FROM permission WHERE code = ANY(:c)"), {"r": rid, "c": codes})
    conn.execute(sa.text("INSERT INTO tenant_member (id, tenant_id, user_id, created_at) SELECT gen_random_uuid(), :t, id, now() FROM \"user\""), {"t": tid})
    # superusers (incl. FIRST_SUPERUSER) -> owner, everyone else -> member
    conn.execute(sa.text(
        "INSERT INTO member_role (member_id, role_id) SELECT m.id, CASE WHEN u.is_superuser THEN :o ELSE :m END "
        "FROM tenant_member m JOIN \"user\" u ON u.id = m.user_id WHERE m.tenant_id = :t"),
        {"o": role_ids["owner"], "m": role_ids["member"], "t": tid})

    # item.tenant_id: add nullable, backfill, then NOT NULL + FK + index
    op.add_column("item", sa.Column("tenant_id", sa.Uuid(), nullable=True))
    conn.execute(sa.text("UPDATE item SET tenant_id = :t"), {"t": tid})
    op.alter_column("item", "tenant_id", nullable=False)
    op.create_foreign_key("item_tenant_id_fkey", "item", "tenant", ["tenant_id"], ["id"], ondelete="CASCADE")
    op.create_index(op.f("ix_item_tenant_id"), "item", ["tenant_id"])

    # Row level security backstop. FORCE makes it apply to the table owner as well
    # (Postgres superusers / BYPASSRLS roles still bypass it - the app must not use one).
    op.execute("ALTER TABLE item ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE item FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON item USING ({RLS_EXPR}) WITH CHECK ({RLS_EXPR})")


def downgrade():
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON item")
    op.execute("ALTER TABLE item NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE item DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f("ix_item_tenant_id"), table_name="item")
    op.drop_constraint("item_tenant_id_fkey", "item", type_="foreignkey")
    op.drop_column("item", "tenant_id")
    op.drop_table("member_role")
    op.execute("DELETE FROM role WHERE tenant_id IS NOT NULL")
    op.drop_constraint("uq_role_tenant_name", "role", type_="unique")
    op.drop_index(op.f("ix_role_name"), table_name="role")
    op.create_index("ix_role_name", "role", ["name"], unique=True)
    op.drop_index(op.f("ix_role_tenant_id"), table_name="role")
    op.drop_constraint("role_tenant_id_fkey", "role", type_="foreignkey")
    op.drop_column("role", "tenant_id")
    op.execute("DELETE FROM permission WHERE code = ANY(ARRAY['tenant:manage','members:read','members:write','tenants:read','tenants:write'])")
    op.drop_column("permission", "scope")
    op.drop_index(op.f("ix_tenant_member_user_id"), table_name="tenant_member")
    op.drop_index(op.f("ix_tenant_member_tenant_id"), table_name="tenant_member")
    op.drop_table("tenant_member")
    op.drop_index(op.f("ix_tenant_slug"), table_name="tenant")
    op.drop_table("tenant")
