"""D58 / D59：报警不 Hold、报警码只切设备状态；E10 履历加 trigger

- mes_e10_history 加 trigger（manual / equipment / system），回填：source manual → manual，
  auto → system，其余（equipment / eap / simulator）→ equipment。
- mes_alarm_code：加 target_state（E10 状态编码）；action 收敛为 none / set_state：
  hold_lot → none；hold_equipment / hold_both → set_state，target_state 取原 target_e10_state
  的编码，没有就取本租户的 UDT，再没有就 action=none；删除 target_e10_state_id、hold_reason_id。
- mes_alarm_log.action 同样映射（历史记录，hold_lot → none，其余 hold_* → set_state）。
- 降级：action none → hold_lot、set_state → hold_equipment；按编码回填 target_e10_state_id；
  hold_reason_id 恢复为空；删除 target_state、trigger。
升级 / 降级均可重复执行。

Revision ID: 0029_d58_alarm_state
Revises: 0028_eap_events_idempotency
"""

import sqlalchemy as sa
from alembic import op

revision = "0029_d58_alarm_state"
down_revision = "0028_eap_events_idempotency"
branch_labels = None
depends_on = None

H, CODE, LOG = "mes_e10_history", "mes_alarm_code", "mes_alarm_log"


def _cols(t: str) -> set[str]:
    i = sa.inspect(op.get_bind())
    return {c["name"] for c in i.get_columns(t)} if i.has_table(t) else set()


def upgrade():
    if "trigger" not in _cols(H) and _cols(H):
        op.add_column(H, sa.Column("trigger", sa.String(40), nullable=True))
        op.execute(
            f"UPDATE {H} SET trigger = CASE source WHEN 'manual' THEN 'manual' "
            "WHEN 'auto' THEN 'system' ELSE 'equipment' END"
        )
    have = _cols(CODE)
    if have and "target_state" not in have:
        op.add_column(CODE, sa.Column("target_state", sa.String(40), nullable=True))
        op.execute(
            f"""
            UPDATE {CODE} c SET target_state = COALESCE(
                (SELECT s.code FROM mes_e10_state s WHERE s.id = c.target_e10_state_id),
                (SELECT s.code FROM mes_e10_state s
                  WHERE s.tenant_id = c.tenant_id AND s.code = 'UDT' LIMIT 1))
            WHERE c.action IN ('hold_equipment', 'hold_both')
            """
        )
        op.execute(
            f"UPDATE {CODE} SET action = CASE WHEN action IN ('hold_equipment', 'hold_both') "
            "AND target_state IS NOT NULL THEN 'set_state' ELSE 'none' END, "
            "target_state = CASE WHEN action IN ('hold_equipment', 'hold_both') "
            "THEN target_state END"
        )
        for c in ("target_e10_state_id", "hold_reason_id"):
            if c in have:
                op.drop_column(CODE, c)
    if _cols(LOG):
        op.execute(
            f"UPDATE {LOG} SET action = CASE WHEN action IN ('hold_equipment', 'hold_both') "
            "THEN 'set_state' WHEN action = 'hold_lot' THEN 'none' ELSE action END"
        )


def downgrade():
    have = _cols(CODE)
    if have and "target_state" in have:
        for c, ref in (
            ("target_e10_state_id", "mes_e10_state"),
            ("hold_reason_id", "mes_reason_code"),
        ):
            if c not in have:
                op.add_column(CODE, sa.Column(c, sa.Uuid(), nullable=True))
                op.create_foreign_key(None, CODE, ref, [c], ["id"], ondelete="RESTRICT")
                op.create_index(op.f(f"ix_{CODE}_{c}"), CODE, [c], unique=False)
        op.execute(
            f"""
            UPDATE {CODE} c SET target_e10_state_id = (
                SELECT s.id FROM mes_e10_state s
                 WHERE s.tenant_id = c.tenant_id AND s.code = c.target_state LIMIT 1),
              action = CASE action WHEN 'set_state' THEN 'hold_equipment'
                                   WHEN 'none' THEN 'hold_lot' ELSE action END
            """
        )
        op.drop_column(CODE, "target_state")
    if _cols(LOG):
        op.execute(
            f"UPDATE {LOG} SET action = CASE action WHEN 'set_state' THEN 'hold_equipment' "
            "WHEN 'none' THEN 'hold_lot' ELSE action END"
        )
    if "trigger" in _cols(H):
        op.drop_column(H, "trigger")
