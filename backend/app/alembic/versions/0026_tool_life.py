"""P2-B10 耗材 / 工装寿命：计数改 numeric(18,6)、类型与实例加字段、两张履历表

- mes_tool.usage_count / max_usage、mes_fixture.max_uses：integer → numeric(18,6)，旧整数原样
  保留（5 → 5.000000）。降级（OQ-6）：ROUND（四舍五入）回整数，小数部分丢失。
- mes_fixture 加 consumable_kind / life_unit（默认 use）/ count_basis（默认 per_track_out）/
  warn_ratio / require_qual_on_replace（默认 false）；现有行回填默认值，行为不变。
- mes_tool 加 warn_ratio（空 = 取类型值，再取 warn_pct/100，默认 0.9，D54）/ sub_unit_id / mounted_at / life_reset_count。
- 新表 mes_tool_usage（计数履历，uq_mes_tool_usage_event (tenant, source, external_event_id)）、
  mes_tool_mount_log（装卸 / 更换，uq_mes_tool_mount_open (tenant, tool_id) WHERE
  unmounted_at IS NULL）；均启用 RLS。
升级 / 降级均可重复执行。

Revision ID: 0026_tool_life
Revises: 0025_alarm
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0026_tool_life"
down_revision = "0025_alarm"
branch_labels = None
depends_on = None

TOOL, FIX, USE, MNT = "mes_tool", "mes_fixture", "mes_tool_usage", "mes_tool_mount_log"
NUM = sa.Numeric(18, 6)
DT = sa.DateTime(timezone=True)
S = sa.String
NUMERIC_COLS = ((TOOL, "usage_count"), (TOOL, "max_usage"), (FIX, "max_uses"))
FIX_COLS: list[tuple[str, sa.types.TypeEngine, str | None]] = [
    ("consumable_kind", S(40), "'other'"),
    ("life_unit", S(40), "'use'"),
    ("count_basis", S(40), "'per_track_out'"),
    ("warn_ratio", sa.Numeric(18, 4), None),
    ("require_qual_on_replace", sa.Boolean(), "false"),
]
TOOL_COLS: list[tuple[str, sa.types.TypeEngine, str | None]] = [
    ("warn_ratio", sa.Numeric(18, 4), None),
    ("sub_unit_id", sa.Uuid(), None),
    ("mounted_at", DT, None),
    ("life_reset_count", sa.Integer(), "0"),
]


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


def _source() -> list[sa.Column]:
    return [
        sa.Column("comment", S(300), nullable=True),
        sa.Column("source", S(40), nullable=False),
        sa.Column("external_event_id", S(128), nullable=True),
        sa.Column("username", S(255), nullable=True),
    ]


def upgrade():
    for t, c in NUMERIC_COLS:
        if not isinstance(_cols(t)[c], sa.Numeric):
            op.alter_column(t, c, type_=NUM, postgresql_using=f"{c}::numeric(18,6)")
    for t, cols in ((FIX, FIX_COLS), (TOOL, TOOL_COLS)):
        have = _cols(t)
        for c, typ, default in cols:
            if c in have:
                continue
            op.add_column(t, sa.Column(c, typ, nullable=True))
            if default is not None:
                op.execute(f"UPDATE {t} SET {c} = {default}")
            if c == "sub_unit_id":
                op.create_foreign_key(
                    f"{t}_sub_unit_id_fkey", t, "mes_equipment", [c], ["id"],
                    ondelete="RESTRICT",
                )
                op.create_index(op.f(f"ix_{t}_sub_unit_id"), t, [c], unique=False)
    tables = set(_insp().get_table_names())
    if USE not in tables:
        _create(
            USE,
            *_ref("tool_id", TOOL, required=True, cascade=True),
            *_ref("equipment_id", "mes_equipment"),
            *_ref("sub_unit_id", "mes_equipment"),
            *_ref("lot_id", "mes_lot"),
            *_ref("operation_id", "mes_operation"),
            sa.Column("delta", NUM, nullable=False),
            sa.Column("count_after", NUM, nullable=True),
            sa.Column("kind", S(40), nullable=False),
            sa.Column("occurred_at", DT, nullable=False),
            *_ref("reason_id", "mes_reason_code"),
            *_source(),
            refs=("tool_id", "equipment_id", "sub_unit_id", "lot_id", "operation_id",
                  "reason_id"),
        )
        op.create_index(
            "uq_mes_tool_usage_event", USE, ["tenant_id", "source", "external_event_id"],
            unique=True, postgresql_where=sa.text("external_event_id IS NOT NULL"),
        )
    if MNT not in tables:
        _create(
            MNT,
            *_ref("tool_id", TOOL, required=True, cascade=True),
            *_ref("equipment_id", "mes_equipment", required=True),
            *_ref("sub_unit_id", "mes_equipment"),
            sa.Column("port_code", S(64), nullable=True),
            sa.Column("mounted_at", DT, nullable=False),
            sa.Column("unmounted_at", DT, nullable=True),
            sa.Column("unmount_reason", S(40), nullable=True),
            *_ref("replaced_by_tool_id", TOOL),
            sa.Column("usage_at_mount", NUM, nullable=True),
            sa.Column("usage_at_unmount", NUM, nullable=True),
            *_source(),
            refs=("tool_id", "equipment_id", "sub_unit_id", "replaced_by_tool_id"),
        )
        op.create_index(
            "uq_mes_tool_mount_open", MNT, ["tenant_id", "tool_id"], unique=True,
            postgresql_where=sa.text("unmounted_at IS NULL"),
        )


def downgrade():
    tables = set(_insp().get_table_names())
    for t in (MNT, USE):
        if t in tables:
            disable_rls(op, [t])
            op.drop_table(t)
    for t, cols in ((TOOL, TOOL_COLS), (FIX, FIX_COLS)):
        have = _cols(t)
        for c, _typ, _d in reversed(cols):
            if c in have:
                if c == "sub_unit_id":
                    op.drop_index(op.f(f"ix_{t}_sub_unit_id"), table_name=t)
                op.drop_column(t, c)
    for t, c in NUMERIC_COLS:
        if isinstance(_cols(t)[c], sa.Numeric):
            # OQ-6：小数四舍五入回整数
            op.alter_column(
                t, c, type_=sa.Integer(), postgresql_using=f"ROUND({c})::integer"
            )
