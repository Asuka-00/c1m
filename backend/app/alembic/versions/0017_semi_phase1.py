"""泛半导体阶段 1：单元转换谱系、芯片级晶圆图、Wafer / Die Bank、NCR / MRB、SPC 判异。

新表 ``mes_bank`` / ``mes_bin_code`` / ``mes_die_map`` / ``mes_unit_genealogy`` /
``mes_ncr`` / ``mes_ncr_approval``；``mes_lot.bank_id`` / ``banked_at``、
``mes_measurement_item.ooc_action`` / ``ooc_e10_state_id``、
``mes_dc_plan_item`` 控制限与判异规则、``mes_dc_result.is_ooc`` / ``ooc_rules``。

Revision ID: 0017_semi_phase1
Revises: 0016_shipment_inbound
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0017_semi_phase1"
down_revision = "0016_shipment_inbound"
branch_labels = None
depends_on = None

TABLES = [
    "mes_bin_code",
    "mes_bank",
    "mes_die_map",
    "mes_unit_genealogy",
    "mes_ncr",
    "mes_ncr_approval",
]
COLUMNS = [
    ("mes_dc_plan_item", sa.Column("lcl", sa.Float(), nullable=True)),
    ("mes_dc_plan_item", sa.Column("cl", sa.Float(), nullable=True)),
    ("mes_dc_plan_item", sa.Column("ucl", sa.Float(), nullable=True)),
    ("mes_dc_plan_item", sa.Column("ooc_rules", sa.String(length=40), nullable=True)),
    ("mes_dc_result", sa.Column("is_ooc", sa.Boolean(), nullable=True)),
    ("mes_dc_result", sa.Column("ooc_rules", sa.String(length=40), nullable=True)),
    ("mes_lot", sa.Column("banked_at", sa.DateTime(timezone=True), nullable=True)),
    (
        "mes_measurement_item",
        sa.Column("ooc_action", sa.String(length=40), nullable=True),
    ),
]
# (表, 列, 引用表)
REFS = [
    ("mes_lot", "bank_id", "mes_bank"),
    ("mes_measurement_item", "ooc_e10_state_id", "mes_e10_state"),
]


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_col(table: str, col: str) -> bool:
    return any(c["name"] == col for c in sa.inspect(op.get_bind()).get_columns(table))


def _fk(col: str, target: str, ondelete: str = "RESTRICT") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [f"{target}.id"], ondelete=ondelete)


def _table(name: str, *items: sa.Column | sa.Constraint, coded: bool = False) -> None:
    """建表：补齐 id / tenant_id / 审计列，并为租户与引用列建索引。"""
    head = [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
    ]
    if coded:
        head.append(sa.Column("code", sa.String(length=64), nullable=False))
    tail = [
        sa.Column("attrs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        _fk("tenant_id", "tenant", "CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    ]
    if coded:
        tail.append(
            sa.UniqueConstraint(
                "tenant_id",
                "code",
                name=f"uq_{name}_0",
                postgresql_nulls_not_distinct=True,
            )
        )
    op.create_table(name, *head, *items, *tail)
    cols = ["tenant_id"] + [
        c.name for c in items if isinstance(c, sa.Column) and c.name.endswith("_id")
    ]
    for c in sorted(cols):
        op.create_index(op.f(f"ix_{name}_{c}"), name, [c], unique=False)


def _who() -> list[sa.Column]:
    return [
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade():
    if not _has_table(TABLES[0]):  # stamp 后重复升级：表已存在
        _table(
            "mes_bin_code",
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("is_good", sa.Boolean(), nullable=True),
            sa.Column("color", sa.String(length=20), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            coded=True,
        )
        _table(
            "mes_bank",
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("bank_kind", sa.String(length=40), nullable=False),
            sa.Column("warehouse_id", sa.Uuid(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            _fk("warehouse_id", "mes_warehouse"),
            coded=True,
        )
        _table(
            "mes_die_map",
            sa.Column("unit_id", sa.Uuid(), nullable=False),
            sa.Column("lot_id", sa.Uuid(), nullable=False),
            sa.Column("route_step_id", sa.Uuid(), nullable=True),
            sa.Column("test_kind", sa.String(length=40), nullable=False),
            sa.Column("rows", sa.Integer(), nullable=True),
            sa.Column("cols", sa.Integer(), nullable=True),
            sa.Column("dies", sa.JSON(), nullable=True),
            sa.Column("gross", sa.Integer(), nullable=True),
            sa.Column("good", sa.Integer(), nullable=True),
            sa.Column("yield_pct", sa.Float(), nullable=True),
            sa.Column("is_current", sa.Boolean(), nullable=True),
            sa.Column("source", sa.String(length=200), nullable=True),
            *_who(),
            _fk("unit_id", "mes_wafer", "CASCADE"),
            _fk("lot_id", "mes_lot", "CASCADE"),
            _fk("route_step_id", "mes_route_step"),
        )
        _table(
            "mes_unit_genealogy",
            sa.Column("parent_unit_id", sa.Uuid(), nullable=False),
            sa.Column("child_unit_id", sa.Uuid(), nullable=False),
            sa.Column("lot_id", sa.Uuid(), nullable=False),
            sa.Column("relation", sa.String(length=40), nullable=True),
            sa.Column("qty", sa.Integer(), nullable=True),
            sa.Column("dies", sa.JSON(), nullable=True),
            sa.Column("route_step_id", sa.Uuid(), nullable=True),
            *_who(),
            _fk("parent_unit_id", "mes_wafer", "CASCADE"),
            _fk("child_unit_id", "mes_wafer", "CASCADE"),
            _fk("lot_id", "mes_lot", "CASCADE"),
            _fk("route_step_id", "mes_route_step"),
        )
        _table(
            "mes_ncr",
            sa.Column("lot_id", sa.Uuid(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("severity", sa.String(length=40), nullable=False),
            sa.Column("defect_code_id", sa.Uuid(), nullable=True),
            sa.Column("qty", sa.Integer(), nullable=True),
            sa.Column("units", sa.JSON(), nullable=True),
            sa.Column("hold_id", sa.Uuid(), nullable=True),
            sa.Column("ncr_status", sa.String(length=40), nullable=True),
            sa.Column("disposition", sa.String(length=40), nullable=True),
            sa.Column("disposition_comment", sa.String(length=300), nullable=True),
            sa.Column("scrap_reason_id", sa.Uuid(), nullable=True),
            sa.Column("required_levels", sa.Integer(), nullable=True),
            sa.Column("approved_levels", sa.Integer(), nullable=True),
            sa.Column("raised_by", sa.String(length=255), nullable=True),
            sa.Column("raised_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("proposed_by", sa.String(length=255), nullable=True),
            sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_by", sa.String(length=255), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            _fk("lot_id", "mes_lot", "CASCADE"),
            _fk("defect_code_id", "mes_defect_code"),
            _fk("hold_id", "mes_lot_hold"),
            _fk("scrap_reason_id", "mes_reason_code"),
            coded=True,
        )
        _table(
            "mes_ncr_approval",
            sa.Column("ncr_id", sa.Uuid(), nullable=False),
            sa.Column("level", sa.Integer(), nullable=True),
            sa.Column("decision", sa.String(length=40), nullable=True),
            sa.Column("comment", sa.String(length=300), nullable=True),
            *_who(),
            _fk("ncr_id", "mes_ncr", "CASCADE"),
        )
        enable_rls(op, TABLES)
    for table, col in COLUMNS:
        if not _has_col(table, col.name):
            op.add_column(table, col)
    for table, col, target in REFS:
        if _has_col(table, col):
            continue
        op.add_column(table, sa.Column(col, sa.Uuid(), nullable=True))
        op.create_index(op.f(f"ix_{table}_{col}"), table, [col])
        op.create_foreign_key(
            f"fk_{table}_{col}", table, target, [col], ["id"], ondelete="RESTRICT"
        )


def downgrade():
    for table, col, _ in reversed(REFS):
        if _has_col(table, col):
            op.drop_constraint(f"fk_{table}_{col}", table, type_="foreignkey")
            op.drop_index(op.f(f"ix_{table}_{col}"), table_name=table)
            op.drop_column(table, col)
    for table, col in reversed(COLUMNS):
        if _has_col(table, col.name):
            op.drop_column(table, col.name)
    present = [t for t in TABLES if _has_table(t)]
    disable_rls(op, present)
    for t in reversed(present):
        op.drop_table(t)
