"""hold qtime fields (D20)

Q-Time 自动 Hold 记录的附加列：qtime_rule_id、qtime_from_step_id、qtime_to_step_id、
qtime_overdue_seconds，均可空（手动 Hold 与旧记录为空）。升级 / 降级均可重复执行。

Revision ID: 0009_hold_qtime_fields
Revises: 0008_system_reason_codes
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_hold_qtime_fields"
down_revision = "0008_system_reason_codes"
branch_labels = None
depends_on = None

T = "mes_lot_hold"
REFS = {
    "qtime_rule_id": "mes_qtime_rule",
    "qtime_from_step_id": "mes_route_step",
    "qtime_to_step_id": "mes_route_step",
}


def _cols() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(T)}


def upgrade():
    have = _cols()
    for col, ref in REFS.items():
        if col in have:
            continue
        op.add_column(T, sa.Column(col, sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"{T}_{col}_fkey", T, ref, [col], ["id"], ondelete="RESTRICT"
        )
        op.create_index(op.f(f"ix_{T}_{col}"), T, [col], unique=False)
    if "qtime_overdue_seconds" not in have:
        op.add_column(T, sa.Column("qtime_overdue_seconds", sa.Integer(), nullable=True))


def downgrade():
    have = _cols()
    if "qtime_overdue_seconds" in have:
        op.drop_column(T, "qtime_overdue_seconds")
    for col in reversed(list(REFS)):
        if col not in have:
            continue
        op.drop_index(op.f(f"ix_{T}_{col}"), table_name=T)
        op.drop_constraint(f"{T}_{col}_fkey", T, type_="foreignkey")
        op.drop_column(T, col)
