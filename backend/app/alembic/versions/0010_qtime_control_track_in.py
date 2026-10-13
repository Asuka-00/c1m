"""qtime control at track in (D23)

Q-Time 管控（check_type=qtime 的严重度 / 开关）从 Move In 时机平移到 Track In：
对每个绑定在 move_in 且方案含 qtime 规则的卡控方案，复制一个只含 qtime 规则的方案
（attrs.d23_from_plan），并按原绑定的作用域新建 track_in 绑定（attrs.d23_from_binding）。
原 move_in 配置保留不动（代码在 Move In 不再读 qtime），downgrade 删除迁移生成的行即恢复。
升级 / 降级都可重复执行。

Revision ID: 0010_qtime_control_track_in
Revises: 0009_hold_qtime_fields
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_qtime_control_track_in"
down_revision = "0009_hold_qtime_fields"
branch_labels = None
depends_on = None

_HAS_QTIME = """
    EXISTS (SELECT 1 FROM mes_check_plan_item i
            JOIN mes_check_rule r ON r.id = i.check_rule_id
            WHERE i.check_plan_id = p.id AND r.check_type = 'qtime')
"""

UPGRADE = [
    # 1) 只含 qtime 规则的新方案（每个源方案一次）
    f"""
    INSERT INTO mes_check_plan (id, tenant_id, code, name, is_active, description,
                                attrs, created_at, updated_at)
    SELECT gen_random_uuid(), p.tenant_id, left(p.code || '-QT-TI', 100),
           left(coalesce(p.name, p.code) || ' (Q-Time @ Track In)', 100), p.is_active,
           'D23: migrated from move_in',
           json_build_object('d23_from_plan', p.id::text), now(), now()
    FROM mes_check_plan p
    WHERE EXISTS (SELECT 1 FROM mes_check_binding b
                  WHERE b.check_plan_id = p.id AND b.trigger = 'move_in')
      AND {_HAS_QTIME}
      AND NOT EXISTS (SELECT 1 FROM mes_check_plan q
                      WHERE q.tenant_id = p.tenant_id
                        AND q.attrs->>'d23_from_plan' = p.id::text)
    ON CONFLICT DO NOTHING
    """,
    # 2) 新方案的规则条目：源方案中的 qtime 规则
    """
    INSERT INTO mes_check_plan_item (id, tenant_id, check_plan_id, check_rule_id, seq,
                                     created_at, updated_at)
    SELECT gen_random_uuid(), q.tenant_id, q.id, i.check_rule_id, i.seq, now(), now()
    FROM mes_check_plan q
    JOIN mes_check_plan_item i ON i.check_plan_id = (q.attrs->>'d23_from_plan')::uuid
    JOIN mes_check_rule r ON r.id = i.check_rule_id AND r.check_type = 'qtime'
    WHERE q.attrs->>'d23_from_plan' IS NOT NULL
    ON CONFLICT DO NOTHING
    """,
    # 3) track_in 绑定：作用域与启用状态同原 move_in 绑定
    """
    INSERT INTO mes_check_binding (id, tenant_id, check_plan_id, trigger, scope,
        route_step_id, equipment_id, operation_id, equipment_type_id, product_id,
        is_active, attrs, created_at, updated_at)
    SELECT gen_random_uuid(), b.tenant_id, q.id, 'track_in', b.scope,
           b.route_step_id, b.equipment_id, b.operation_id, b.equipment_type_id,
           b.product_id, b.is_active, json_build_object('d23_from_binding', b.id::text),
           now(), now()
    FROM mes_check_binding b
    JOIN mes_check_plan q ON q.tenant_id = b.tenant_id
         AND q.attrs->>'d23_from_plan' = b.check_plan_id::text
    WHERE b.trigger = 'move_in'
      AND NOT EXISTS (SELECT 1 FROM mes_check_binding x
                      WHERE x.tenant_id = b.tenant_id
                        AND x.attrs->>'d23_from_binding' = b.id::text)
    ON CONFLICT DO NOTHING
    """,
]

DOWNGRADE = [
    # 卡控记录改指回源方案（保留履历）
    """UPDATE mes_check_log l SET check_plan_id = (q.attrs->>'d23_from_plan')::uuid
       FROM mes_check_plan q
       WHERE l.check_plan_id = q.id AND q.attrs->>'d23_from_plan' IS NOT NULL""",
    "DELETE FROM mes_check_binding WHERE attrs->>'d23_from_binding' IS NOT NULL",
    """DELETE FROM mes_check_plan_item WHERE check_plan_id IN
       (SELECT id FROM mes_check_plan WHERE attrs->>'d23_from_plan' IS NOT NULL)""",
    "DELETE FROM mes_check_plan WHERE attrs->>'d23_from_plan' IS NOT NULL",
]


def upgrade():
    for q in UPGRADE:
        op.execute(sa.text(q))


def downgrade():
    for q in DOWNGRADE:
        op.execute(sa.text(q))
