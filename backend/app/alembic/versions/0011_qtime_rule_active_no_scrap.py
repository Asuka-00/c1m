"""qtime_rule: is_active (D24/D25) + drop scrap action (D26)

- 加启用标志 is_active（默认 true，旧规则全部启用）；被 Hold 引用的规则不能删除，改为停用。
- 加 active_since：停用后重新启用的时间，此前已开始计时的批次不追溯。
- D26：处置为 scrap 的规则改成 hold，原因码保留（可为空，D25）。在 attrs 记
  ``d26_from = "scrap"``，downgrade 据此恢复为 scrap，因此可逆。
升级 / 降级均可重复执行。

Revision ID: 0011_qtime_rule_active_no_scrap
Revises: 0010_qtime_control_track_in
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_qtime_rule_active_no_scrap"
down_revision = "0010_qtime_control_track_in"
branch_labels = None
depends_on = None

T = "mes_qtime_rule"

SCRAP_TO_HOLD = f"""
UPDATE {T}
   SET action = 'hold',
       attrs = (coalesce(attrs::jsonb, '{{}}'::jsonb) || '{{"d26_from": "scrap"}}'::jsonb)::json
 WHERE action = 'scrap'
"""

HOLD_TO_SCRAP = f"""
UPDATE {T}
   SET action = 'scrap', attrs = (attrs::jsonb - 'd26_from')::json
 WHERE attrs->>'d26_from' = 'scrap'
"""


def _has(col: str = "is_active") -> bool:
    cols = sa.inspect(op.get_bind()).get_columns(T)
    return any(c["name"] == col for c in cols)


def upgrade():
    if not _has():
        op.add_column(
            T,
            sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.true()),
        )
        op.execute(sa.text(f"UPDATE {T} SET is_active = true WHERE is_active IS NULL"))
        op.alter_column(T, "is_active", server_default=None)
    if not _has("active_since"):  # 重新启用时间：此前开始计时的批次不追溯
        op.add_column(T, sa.Column("active_since", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text(SCRAP_TO_HOLD))


def downgrade():
    op.execute(sa.text(HOLD_TO_SCRAP))
    if _has("active_since"):
        op.drop_column(T, "active_since")
    if _has():
        op.drop_column(T, "is_active")
