"""P3-B4 光罩：mes_reticle 扩展 + 6 张新表（docs p3-reticle-model v0.8.2，D66–D69）

- mes_reticle：product_id / layer 改可空（v0.4 N-B）；max_shots integer → numeric(18,6)；
  状态值迁移到专用 reticle_status（hold → on_hold，retired → scrapped，D66 Q15 / D68）；
  加 revision、shot_count、mount_count、warn_ratio、life_reset_count、count_basis（默认 track_out）、
  shots_per_wafer_default、received_at（回填 created_at）、first_used_at、storage_location(64)、
  carrier_id、equipment_id、mounted_at、last/next inspection、inspection_interval_*、
  hold_reason、status_before_hold、inspection_required（默认 false）。唯一键仍 uq_mes_reticle_0。
- 新表 mes_reticle_applicability / _incident / _mount_log / _usage / _inspection / _status_log，
  均 tenant_id + RLS（app.core.rls.enable_tenant_rls_sql：ENABLE + FORCE，策略 tenant_isolation）；
  事件表 (tenant_id, source, external_event_id) 部分唯一。
- 已有 mes_reticle.product_id + layer 回填一行 applicability（is_primary=true）。
升级 / 降级均可重复执行；降级 scrapped → retired、on_hold/其他新状态 → hold，max_shots ROUND 回整数。

Revision ID: 0030_p3_reticle
Revises: 0029_d58_alarm_state
"""

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls_sql, enable_tenant_rls_sql

revision = "0030_p3_reticle"
down_revision = "0029_d58_alarm_state"
branch_labels = None
depends_on = None

RT = "mes_reticle"
APP, INC, MNT, USE, INSP, LOG = (
    "mes_reticle_applicability",
    "mes_reticle_incident",
    "mes_reticle_mount_log",
    "mes_reticle_usage",
    "mes_reticle_inspection",
    "mes_reticle_status_log",
)
NEW = (APP, INC, MNT, USE, INSP, LOG)
NUM = sa.Numeric(18, 6)
DT = sa.DateTime(timezone=True)
S = sa.String
# (列, 类型, 回填 SQL 或 None, 外键目标)
RT_COLS: list[tuple[str, sa.types.TypeEngine, str | None, str | None]] = [
    ("revision", S(20), None, None),
    ("shot_count", NUM, "0", None),
    ("mount_count", sa.Integer(), "0", None),
    ("warn_ratio", sa.Numeric(18, 4), None, None),
    ("life_reset_count", sa.Integer(), "0", None),
    ("count_basis", S(40), "'track_out'", None),
    ("shots_per_wafer_default", NUM, None, None),
    ("received_at", DT, "created_at", None),
    ("first_used_at", DT, None, None),
    ("storage_location", S(64), None, None),
    ("carrier_id", sa.Uuid(), None, "mes_carrier"),
    ("equipment_id", sa.Uuid(), None, "mes_equipment"),
    ("mounted_at", DT, None, None),
    ("last_inspected_at", DT, None, None),
    ("next_inspection_due_at", DT, None, None),
    ("inspection_interval_shots", NUM, None, None),
    ("inspection_interval_days", sa.Integer(), None, None),
    ("hold_reason", S(40), None, None),
    ("status_before_hold", S(40), None, None),
    ("inspection_required", sa.Boolean(), "false", None),
]
NOT_NULL = ("count_basis",)


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _cols(t: str) -> dict[str, sa.types.TypeEngine]:
    return {c["name"]: c["type"] for c in _insp().get_columns(t)}


def _sys() -> list[sa.Column]:
    return [
        sa.Column("attrs", sa.JSON(), nullable=True),
        sa.Column("created_at", DT, nullable=True),
        sa.Column("updated_at", DT, nullable=True),
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


def _rt() -> list:
    return _ref("reticle_id", RT, required=True, cascade=True)


def _src() -> list[sa.Column]:
    return [
        sa.Column("source", S(40), nullable=False),
        sa.Column("external_event_id", S(128), nullable=True),
        sa.Column("username", S(255), nullable=True),
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
    for c in ("tenant_id", "reticle_id", *refs):
        op.create_index(op.f(f"ix_{name}_{c}"), name, [c], unique=False)
    for stmt in enable_tenant_rls_sql(name):
        op.execute(stmt)


def _event_uq(name: str, table: str) -> None:
    op.create_index(
        name,
        table,
        ["tenant_id", "source", "external_event_id"],
        unique=True,
        postgresql_where=sa.text("external_event_id IS NOT NULL"),
    )


def _upgrade_reticle() -> None:
    have = _cols(RT)
    for c in ("product_id", "layer"):
        op.alter_column(RT, c, nullable=True)
    if not isinstance(have["max_shots"], sa.Numeric):
        op.alter_column(
            RT, "max_shots", type_=NUM, postgresql_using="max_shots::numeric(18,6)"
        )
    for c, typ, fill, fk in RT_COLS:
        if c in have:
            continue
        op.add_column(RT, sa.Column(c, typ, nullable=True))
        if fill is not None:
            op.execute(f"UPDATE {RT} SET {c} = {fill}")
        if c in NOT_NULL:
            op.alter_column(RT, c, nullable=False)
        if fk:
            op.create_foreign_key(
                f"{RT}_{c}_fkey", RT, fk, [c], ["id"], ondelete="RESTRICT"
            )
            op.create_index(op.f(f"ix_{RT}_{c}"), RT, [c], unique=False)
    op.execute(f"UPDATE {RT} SET status_code = 'on_hold', hold_reason = COALESCE(hold_reason, 'manual'), status_before_hold = COALESCE(status_before_hold, 'available') WHERE status_code = 'hold'")
    op.execute(f"UPDATE {RT} SET status_code = 'scrapped' WHERE status_code = 'retired'")
    op.execute(f"UPDATE {RT} SET status_code = 'available' WHERE status_code IS NULL")


def upgrade():
    _upgrade_reticle()
    tables = set(_insp().get_table_names())
    if APP not in tables:
        _create(
            APP,
            *_rt(),
            *_ref("product_id", "mes_product", required=True),
            sa.Column("layer", S(40), nullable=False),
            sa.Column("shots_per_wafer", NUM, nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=True),
            sa.Column("comment", S(300), nullable=True),
            sa.UniqueConstraint(
                "tenant_id",
                "reticle_id",
                "product_id",
                "layer",
                name=f"uq_{APP}_0",
                postgresql_nulls_not_distinct=True,
            ),
            refs=("product_id",),
        )
        op.execute(
            f"INSERT INTO {APP} (id, tenant_id, reticle_id, product_id, layer, is_primary, created_at, updated_at) "
            f"SELECT gen_random_uuid(), tenant_id, id, product_id, layer, true, now(), now() FROM {RT} "
            "WHERE product_id IS NOT NULL AND layer IS NOT NULL"
        )
    if INC not in tables:
        _create(
            INC,
            *_rt(),
            sa.Column("kind", S(40), nullable=False),
            sa.Column("occurred_at", DT, nullable=False),
            *_ref("equipment_id", "mes_equipment"),
            *_ref("lot_id", "mes_lot"),
            sa.Column("description", S(300), nullable=True),
            *_src(),
            refs=("equipment_id", "lot_id"),
        )
        _event_uq("uq_mes_reticle_incident_event", INC)
    if MNT not in tables:
        _create(
            MNT,
            *_rt(),
            *_ref("equipment_id", "mes_equipment", required=True),
            *_ref("sub_unit_id", "mes_equipment"),
            sa.Column("slot_code", S(64), nullable=True),
            sa.Column("mounted_at", DT, nullable=False),
            sa.Column("unmounted_at", DT, nullable=True),
            sa.Column("unmount_reason", S(40), nullable=True),
            sa.Column("shots_at_mount", NUM, nullable=True),
            sa.Column("shots_at_unmount", NUM, nullable=True),
            sa.Column("comment", S(300), nullable=True),
            *_src(),
            refs=("equipment_id", "sub_unit_id"),
        )
        op.create_index(
            "uq_mes_reticle_mount_open", MNT, ["tenant_id", "reticle_id"], unique=True,
            postgresql_where=sa.text("unmounted_at IS NULL"),
        )
        op.create_index(
            "uq_mes_reticle_slot_open", MNT, ["tenant_id", "equipment_id", "slot_code"],
            unique=True,
            postgresql_where=sa.text("unmounted_at IS NULL AND slot_code IS NOT NULL"),
        )
        _event_uq("uq_mes_reticle_mount_event", MNT)
    if USE not in tables:
        _create(
            USE,
            *_rt(),
            *_ref("equipment_id", "mes_equipment"),
            *_ref("lot_id", "mes_lot"),
            *_ref("operation_id", "mes_operation"),
            sa.Column("delta", NUM, nullable=False),
            sa.Column("count_after", NUM, nullable=True),
            sa.Column("kind", S(40), nullable=False),
            sa.Column("occurred_at", DT, nullable=False),
            *_ref("reason_id", "mes_reason_code"),
            sa.Column("comment", S(300), nullable=True),
            *_src(),
            sa.Column("counted", sa.Boolean(), nullable=True),
            sa.Column("estimated", sa.Boolean(), nullable=True),
            sa.Column("corrected_at", DT, nullable=True),
            sa.Column("estimated_delta", NUM, nullable=True),
            refs=("equipment_id", "lot_id", "operation_id", "reason_id"),
        )
        _event_uq("uq_mes_reticle_usage_event", USE)
    if INSP not in tables:
        _create(
            INSP,
            *_rt(),
            sa.Column("kind", S(40), nullable=False),
            sa.Column("result", S(40), nullable=False),
            sa.Column("defect_count", sa.Integer(), nullable=True),
            sa.Column("measured", sa.JSON(), nullable=True),
            *_ref("equipment_id", "mes_equipment"),
            sa.Column("inspected_at", DT, nullable=False),
            sa.Column("disposition", S(40), nullable=True),
            sa.Column("shots_at_inspection", NUM, nullable=True),
            sa.Column("comment", S(300), nullable=True),
            *_src(),
            refs=("equipment_id",),
        )
        _event_uq("uq_mes_reticle_inspection_event", INSP)
    if LOG not in tables:
        _create(
            LOG,
            *_rt(),
            sa.Column("from_status", S(40), nullable=True),
            sa.Column("to_status", S(40), nullable=False),
            sa.Column("action", S(40), nullable=False),
            sa.Column("hold_reason_from", S(40), nullable=True),
            sa.Column("hold_reason_to", S(40), nullable=True),
            sa.Column("reason", S(300), nullable=True),
            sa.Column("comment", S(300), nullable=True),
            sa.Column("trigger", S(40), nullable=False),
            sa.Column("username", S(255), nullable=True),
            sa.Column("at", DT, nullable=False),
            refs=(),
        )


def downgrade():
    tables = set(_insp().get_table_names())
    for t in reversed(NEW):
        if t in tables:
            for stmt in disable_tenant_rls_sql(t):
                op.execute(stmt)
            op.drop_table(t)
    have = _cols(RT)
    if "hold_reason" in have:
        op.execute(f"UPDATE {RT} SET status_code = 'retired' WHERE status_code = 'scrapped'")
        op.execute(
            f"UPDATE {RT} SET status_code = 'hold' WHERE status_code IN "
            "('on_hold', 'inspecting', 'pending_maintenance')"
        )
    for c, _typ, _fill, fk in reversed(RT_COLS):
        if c in have:
            if fk:
                op.drop_index(op.f(f"ix_{RT}_{c}"), table_name=RT)
            op.drop_column(RT, c)
    if isinstance(have.get("max_shots"), sa.Numeric):
        op.alter_column(
            RT, "max_shots", type_=sa.Integer(), postgresql_using="ROUND(max_shots)::integer"
        )
    # product_id / layer 保持可空：新建光罩可能没有填，强制 NOT NULL 会使降级失败
