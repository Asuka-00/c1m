"""工步自动单元转换：``mes_route_step.convert_to`` / ``convert_mode`` / ``convert_ratio``。

Revision ID: 0018_step_convert
Revises: 0017_semi_phase1
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_step_convert"
down_revision = "0017_semi_phase1"
branch_labels = None
depends_on = None

COLUMNS = [
    sa.Column("convert_to", sa.String(length=40), nullable=True),
    sa.Column("convert_mode", sa.String(length=40), nullable=True),
    sa.Column("convert_ratio", sa.Integer(), nullable=True),
]


def _has_col(col: str) -> bool:
    cols = sa.inspect(op.get_bind()).get_columns("mes_route_step")
    return any(c["name"] == col for c in cols)


def upgrade():
    for col in COLUMNS:
        if not _has_col(col.name):
            op.add_column("mes_route_step", col)


def downgrade():
    for col in reversed(COLUMNS):
        if _has_col(col.name):
            op.drop_column("mes_route_step", col.name)
