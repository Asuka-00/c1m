"""P2-B9 设备报警：mes_alarm_code / mes_alarm_log / mes_alarm_lot + 系统原因码 equipment_alarm

- mes_alarm_code：报警码主数据（按设备类型，可单台覆盖）；部分唯一索引
  uq_mes_alarm_code_type (tenant, equipment_type_id, alid) WHERE equipment_id IS NULL、
  uq_mes_alarm_code_eqp (tenant, equipment_id, alid) WHERE equipment_id IS NOT NULL。
- mes_alarm_log：报警履历（raw 原始上报、unregistered、联动结果）；
  uq_mes_alarm_log_event (tenant, source, external_event_id) WHERE external_event_id IS NOT NULL（D30）；
  uq_mes_alarm_log_active (tenant, equipment_id, alid) WHERE alarm_status = 'active'。
- mes_alarm_lot：报警关联批次（alarm_log_id CASCADE、lot_id RESTRICT、唯一 (tenant, alarm_log_id, lot_id)）。
- 为现有租户补建 hold 系统原因码 equipment_alarm（新租户由 seed_system_reasons 创建）。
全部启用 RLS。升级 / 降级均可重复执行。

Revision ID: 0025_alarm
Revises: 0024_bin_split
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0025_alarm"
down_revision = "0024_bin_split"
branch_labels = None
depends_on = None

CODE, LOG, LOT = "mes_alarm_code", "mes_alarm_log", "mes_alarm_lot"
S, I, B, J, DT = sa.String, sa.Integer, sa.Boolean, sa.JSON, sa.DateTime


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _sys() -> list[sa.Column]:
    return [
        sa.Column("attrs", J(), nullable=True),
        sa.Column("created_at", DT(timezone=True), nullable=True),
        sa.Column("updated_at", DT(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    ]


def _ref(col: str, target: str, required: bool = False, cascade: bool = False) -> list:
    return [
        sa.Column(col, sa.Uuid(), nullable=not required),
        sa.ForeignKeyConstraint(
            [col], [f"{target}.id"], ondelete="CASCADE" if cascade else "RESTRICT"
        ),
    ]


def _create(name: str, *items: object, refs: tuple[str, ...]) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        *items,
        *_sys(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for c in ("tenant_id", *refs):
        op.create_index(op.f(f"ix_{name}_{c}"), name, [c], unique=False)
    enable_rls(op, [name])


def _partial(name: str, table: str, cols: list[str], where: str) -> None:
    op.create_index(
        name, table, ["tenant_id", *cols], unique=True, postgresql_where=sa.text(where)
    )


SEED = """
INSERT INTO mes_reason_code
    (id, tenant_id, code, name, reason_type, comment_required, is_active,
     attrs, created_at, updated_at)
SELECT gen_random_uuid(), t.id, 'equipment_alarm', '设备报警', 'hold', false, true,
       '{"system": true}'::json, now(), now()
FROM tenant t
ON CONFLICT ON CONSTRAINT uq_mes_reason_code_0 DO NOTHING
"""


def upgrade():
    have = _tables()
    if CODE not in have:
        _create(
            CODE,
            *_ref("equipment_type_id", "mes_equipment_type", required=True),
            *_ref("equipment_id", "mes_equipment"),
            sa.Column("alid", S(32), nullable=False),
            sa.Column("alcd_category", I(), nullable=True),
            sa.Column("severity", S(40), nullable=False),
            sa.Column("text_en", S(300), nullable=True),
            sa.Column("text_zh", S(300), nullable=True),
            sa.Column("text_ja", S(300), nullable=True),
            sa.Column("category", S(40), nullable=True),
            sa.Column("action", S(40), nullable=False),
            *_ref("target_e10_state_id", "mes_e10_state"),
            *_ref("hold_reason_id", "mes_reason_code"),
            sa.Column("require_qual_on_clear", B(), nullable=True),
            sa.Column("disposition", sa.Text(), nullable=True),
            sa.Column("is_active", B(), nullable=True),
            refs=("equipment_type_id", "equipment_id", "target_e10_state_id",
                  "hold_reason_id"),
        )
        _partial("uq_mes_alarm_code_type", CODE, ["equipment_type_id", "alid"],
                 "equipment_id IS NULL")
        _partial("uq_mes_alarm_code_eqp", CODE, ["equipment_id", "alid"],
                 "equipment_id IS NOT NULL")
    if LOG not in have:
        _create(
            LOG,
            *_ref("equipment_id", "mes_equipment", required=True),
            *_ref("sub_unit_id", "mes_equipment"),
            *_ref("alarm_code_id", "mes_alarm_code"),
            sa.Column("unregistered", B(), nullable=True),
            sa.Column("alid", S(32), nullable=False),
            sa.Column("alcd_raw", I(), nullable=True),
            sa.Column("alarm_text", S(300), nullable=True),
            sa.Column("severity", S(40), nullable=True),
            sa.Column("action", S(40), nullable=True),
            sa.Column("alarm_status", S(40), nullable=False),
            sa.Column("set_at", DT(timezone=True), nullable=False),
            sa.Column("cleared_at", DT(timezone=True), nullable=True),
            sa.Column("cleared_by", S(255), nullable=True),
            sa.Column("clear_source", S(40), nullable=True),
            sa.Column("clear_event_id", S(128), nullable=True),
            sa.Column("hold_ids", J(), nullable=True),
            sa.Column("e10_change", J(), nullable=True),
            sa.Column("raw", J(), nullable=True),
            sa.Column("comment", S(300), nullable=True),
            sa.Column("source", S(40), nullable=False),
            sa.Column("external_event_id", S(128), nullable=True),
            sa.Column("username", S(255), nullable=True),
            refs=("equipment_id", "sub_unit_id", "alarm_code_id"),
        )
        _partial("uq_mes_alarm_log_event", LOG, ["source", "external_event_id"],
                 "external_event_id IS NOT NULL")
        _partial("uq_mes_alarm_log_active", LOG, ["equipment_id", "alid"],
                 "alarm_status = 'active'")
    if LOT not in have:
        _create(
            LOT,
            *_ref("alarm_log_id", LOG, required=True, cascade=True),
            *_ref("lot_id", "mes_lot", required=True),
            sa.UniqueConstraint(
                "tenant_id", "alarm_log_id", "lot_id", name="uq_mes_alarm_lot_0",
                postgresql_nulls_not_distinct=True,
            ),
            refs=("alarm_log_id", "lot_id"),
        )
    op.execute(SEED)


def downgrade():
    op.execute(
        """
        DELETE FROM mes_reason_code rc
        WHERE rc.code = 'equipment_alarm' AND rc.reason_type = 'hold'
          AND NOT EXISTS (SELECT 1 FROM mes_lot_hold h WHERE h.reason_id = rc.id)
        """
    )
    have = _tables()
    for name in (LOT, LOG, CODE):
        if name in have:
            disable_rls(op, [name])
            op.drop_table(name)
