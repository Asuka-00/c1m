"""Add menu table (backend-driven navigation / routes)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-10 17:10:00

"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    S = sqlmodel.sql.sqltypes.AutoString
    op.create_table(
        "menu",
        sa.Column("key", S(length=100), nullable=False),
        sa.Column("title", S(length=100), nullable=False),
        sa.Column("path", S(length=255), nullable=True),
        sa.Column("icon", S(length=50), nullable=True),
        sa.Column("component", S(length=100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("permission", S(length=100), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["menu.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_menu_key"), "menu", ["key"], unique=True)
    op.create_index(op.f("ix_menu_parent_id"), "menu", ["parent_id"])
    # default rows are seeded idempotently by app.menus.seed_menus (initial_data.py)


def downgrade():
    op.drop_index(op.f("ix_menu_parent_id"), table_name="menu")
    op.drop_index(op.f("ix_menu_key"), table_name="menu")
    op.drop_table("menu")
