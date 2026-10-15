"""D71 补充：mes_reticle_inspection 去掉 source / external_event_id 与部分唯一索引，
disposition 改 NOT NULL DEFAULT 'none'（先回填 NULL）。

Revision ID: 0031_d71_reticle_inspection
Revises: 0030_p3_reticle
"""

import sqlalchemy as sa
from alembic import op

revision = "0031_d71_reticle_inspection"
down_revision = "0030_p3_reticle"
branch_labels = None
depends_on = None

T = "mes_reticle_inspection"
UQ = "uq_mes_reticle_inspection_event"


def _has_table() -> bool:
    return T in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _has_table():
        return
    op.execute(f"DROP INDEX IF EXISTS {UQ}")
    op.execute(f"ALTER TABLE {T} DROP COLUMN IF EXISTS external_event_id")
    op.execute(f"ALTER TABLE {T} DROP COLUMN IF EXISTS source")
    op.execute(f"UPDATE {T} SET disposition = 'none' WHERE disposition IS NULL")
    op.alter_column(
        T,
        "disposition",
        existing_type=sa.String(40),
        nullable=False,
        server_default=sa.text("'none'"),
    )


def downgrade():
    if not _has_table():
        return
    op.alter_column(
        T,
        "disposition",
        existing_type=sa.String(40),
        nullable=True,
        server_default=None,
    )
    op.add_column(
        T,
        sa.Column("source", sa.String(40), nullable=False, server_default="manual"),
    )
    op.alter_column(T, "source", server_default=None)
    op.add_column(T, sa.Column("external_event_id", sa.String(128), nullable=True))
    op.create_index(
        UQ,
        T,
        ["tenant_id", "source", "external_event_id"],
        unique=True,
        postgresql_where=sa.text("external_event_id IS NOT NULL"),
    )
