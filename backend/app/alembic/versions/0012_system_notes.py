"""系统生成说明的结构化列 ``note``：Hold 记录与 E10 履历

系统自动产生的说明（Q-Time 超时 Hold、OOS Hold、分批继承 Hold、E10 自动迁移）不再把英文
拼进备注，而是存 ``{key, params}``，前端按语言包翻译。人工备注仍在 ``comment``。

Revision ID: 0012_system_notes
Revises: 0011_qtime_rule_active_no_scrap
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_system_notes"
down_revision = "0011_qtime_rule_active_no_scrap"
branch_labels = None
depends_on = None

TABLES = ("mes_lot_hold", "mes_e10_history")


def _has(table: str) -> bool:
    cols = sa.inspect(op.get_bind()).get_columns(table)
    return any(c["name"] == "note" for c in cols)


def upgrade():
    for t in TABLES:
        if not _has(t):
            op.add_column(t, sa.Column("note", sa.JSON(), nullable=True))


def downgrade():
    for t in TABLES:
        if _has(t):
            op.drop_column(t, "note")
