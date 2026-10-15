"""system reason codes: qtime_expired (D18)

为现有租户补建系统原因码 qtime_expired（hold）；ON CONFLICT DO NOTHING，可重复执行。
新租户由 app.mes.execution.seed.seed_system_reasons 在初始化时创建。

Revision ID: 0008_system_reason_codes
Revises: 0007_operator_qual
Create Date: 2026-10-13 19:00:00
"""

from alembic import op

revision = "0008_system_reason_codes"
down_revision = "0007_operator_qual"
branch_labels = None
depends_on = None

SQL = """
INSERT INTO mes_reason_code
    (id, tenant_id, code, name, reason_type, comment_required, is_active,
     attrs, created_at, updated_at)
SELECT gen_random_uuid(), t.id, 'qtime_expired', 'Q-Time 超时', 'hold', false, true,
       '{"system": true}'::json, now(), now()
FROM tenant t
ON CONFLICT ON CONSTRAINT uq_mes_reason_code_0 DO NOTHING
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    # 只删未被引用的系统原因码，已被 Hold 记录引用的保留
    op.execute(
        """
        DELETE FROM mes_reason_code rc
        WHERE rc.code = 'qtime_expired' AND rc.reason_type = 'hold'
          AND NOT EXISTS (SELECT 1 FROM mes_lot_hold h WHERE h.reason_id = rc.id)
        """
    )
