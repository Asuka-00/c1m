"""P2-B6 / D54-2：撤销转换保留记录，mes_unit_transform 加 undone_at / undone_by / undo_reason。

升级 / 降级均可重复执行。降级只删列（已撤销的转换记录仍留在表里，看起来像未撤销）。

Revision ID: 0027_transform_undone
Revises: 0026_tool_life
"""

import sqlalchemy as sa
from alembic import op

revision = "0027_transform_undone"
down_revision = "0026_tool_life"
branch_labels = None
depends_on = None

T = "mes_unit_transform"
COLS: list[tuple[str, sa.types.TypeEngine]] = [
    ("undone_at", sa.DateTime(timezone=True)),
    ("undone_by", sa.String(255)),
    ("undo_reason", sa.String(300)),
]


def _cols() -> set[str] | None:
    i = sa.inspect(op.get_bind())
    if not i.has_table(T):  # 往返测试里表可能已被更早的降级删掉
        return None
    return {c["name"] for c in i.get_columns(T)}


def upgrade() -> None:
    have = _cols()
    if have is None:
        return
    for name, typ in COLS:
        if name not in have:
            op.add_column(T, sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    have = _cols()
    if have is None:
        return
    for name, _ in reversed(COLS):
        if name in have:
            op.drop_column(T, name)
