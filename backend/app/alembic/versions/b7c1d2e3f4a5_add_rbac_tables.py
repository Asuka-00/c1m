"""Add RBAC tables (role, permission, user_role, role_permission) and seed defaults

Revision ID: b7c1d2e3f4a5
Revises: fe56fa70289e
Create Date: 2026-10-10 16:40:00

"""
import uuid

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "b7c1d2e3f4a5"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None

PERMS = {
    "users:read": "Read any user",
    "users:write": "Create/update any user",
    "users:delete": "Delete any user",
    "items:read": "Read own items",
    "items:write": "Create/update own items",
    "items:delete": "Delete own items",
    "items:read_all": "Read all users' items",
    "roles:read": "Read roles and permissions",
    "roles:write": "Manage roles, permissions and assignments",
}
ROLES = {
    "admin": ("Administrator with all permissions", list(PERMS)),
    "user": ("Regular user", ["items:read", "items:write", "items:delete"]),
}


def upgrade():
    S = sqlmodel.sql.sqltypes.AutoString
    perm = op.create_table(
        "permission",
        sa.Column("code", S(length=100), nullable=False),
        sa.Column("description", S(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_permission_code"), "permission", ["code"], unique=True)
    role = op.create_table(
        "role",
        sa.Column("name", S(length=100), nullable=False),
        sa.Column("description", S(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_role_name"), "role", ["name"], unique=True)
    rp = op.create_table(
        "role_permission",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permission.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    ur = op.create_table(
        "user_role",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    # seed
    pid = {c: uuid.uuid4() for c in PERMS}
    rid = {r: uuid.uuid4() for r in ROLES}
    op.bulk_insert(perm, [{"id": pid[c], "code": c, "description": d} for c, d in PERMS.items()])
    op.bulk_insert(role, [{"id": rid[r], "name": r, "description": d} for r, (d, _) in ROLES.items()])
    op.bulk_insert(rp, [{"role_id": rid[r], "permission_id": pid[c]} for r, (_, cs) in ROLES.items() for c in cs])
    # backfill existing users: superusers -> admin, everyone -> user
    conn = op.get_bind()
    conn.execute(sa.text('INSERT INTO user_role (user_id, role_id) SELECT id, :r FROM "user" WHERE is_superuser'), {"r": rid["admin"]})
    conn.execute(sa.text('INSERT INTO user_role (user_id, role_id) SELECT id, :r FROM "user" WHERE NOT is_superuser'), {"r": rid["user"]})


def downgrade():
    op.drop_table("user_role")
    op.drop_table("role_permission")
    op.drop_index(op.f("ix_role_name"), table_name="role")
    op.drop_table("role")
    op.drop_index(op.f("ix_permission_code"), table_name="permission")
    op.drop_table("permission")
