"""B5 单位转换与谱系：unit_transform / unit_transform_input / unit_transform_output / unit_origin

- mes_unit_transform：一次转换（类型、原因、备注、提示、操作人、UTC 时间）；
  source（非空，人工固定 manual）、external_event_id（可空，预留 EAP），
  部分唯一索引 uq_mes_unit_transform_event (tenant_id, source, external_event_id)
  WHERE external_event_id IS NOT NULL。
- mes_unit_transform_input：每个母批 / 母晶圆的良品来源（map / gross_die / manual）与数量，
  引用当时用到的坐标图版本（不改坐标图表）。
- mes_unit_transform_output：子批、产品、追踪单元类型、数量、颗数。
- mes_unit_origin：子批位置 ← 母批 / 母晶圆 / die 坐标。
lot_status / wafer_status 为字符串列，新增 converted 无需改列。升级 / 降级均可重复执行。

Revision ID: 0022_unit_transform
Revises: 0021_substrate_map
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0022_unit_transform"
down_revision = "0021_substrate_map"
branch_labels = None
depends_on = None

ORDER = [
    "mes_unit_transform",
    "mes_unit_transform_input",
    "mes_unit_transform_output",
    "mes_unit_origin",
]


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
    ]


def _sys() -> list[sa.Column]:
    return [
        sa.Column("attrs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    ]


def _fk(col: str, target: str, cascade: bool = False) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [col], [f"{target}.id"], ondelete="CASCADE" if cascade else "RESTRICT"
    )


def _ix(table: str, *cols: str) -> None:
    for c in cols:
        op.create_index(op.f(f"ix_{table}_{c}"), table, [c], unique=False)


def _create(name: str) -> None:
    S, I = sa.String, sa.Integer
    if name == "mes_unit_transform":
        op.create_table(
            name,
            *_base(),
            sa.Column("transform_type", S(40), nullable=False),
            sa.Column("route_step_id", sa.Uuid(), nullable=True),
            sa.Column("reason_id", sa.Uuid(), nullable=True),
            sa.Column("comment", S(300), nullable=True),
            sa.Column("warnings", sa.JSON(), nullable=True),
            sa.Column("username", S(255), nullable=True),
            sa.Column("at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source", S(40), nullable=False),
            sa.Column("external_event_id", S(128), nullable=True),
            *_sys(),
            _fk("tenant_id", "tenant", True),
            _fk("route_step_id", "mes_route_step"),
            _fk("reason_id", "mes_reason_code"),
            sa.PrimaryKeyConstraint("id"),
        )
        _ix(name, "tenant_id", "route_step_id", "reason_id")
        op.create_index(
            "uq_mes_unit_transform_event",
            name,
            ["tenant_id", "source", "external_event_id"],
            unique=True,
            postgresql_where=sa.text("external_event_id IS NOT NULL"),
        )
    elif name == "mes_unit_transform_input":
        op.create_table(
            name,
            *_base(),
            sa.Column("unit_transform_id", sa.Uuid(), nullable=False),
            sa.Column("lot_id", sa.Uuid(), nullable=False),
            sa.Column("wafer_id", sa.Uuid(), nullable=True),
            sa.Column("substrate_map_id", sa.Uuid(), nullable=True),
            sa.Column("qty_before", I(), nullable=True),
            sa.Column("good_qty", I(), nullable=True),
            sa.Column("fail_qty", I(), nullable=True),
            sa.Column("excluded_qty", I(), nullable=True),
            sa.Column("good_source", S(40), nullable=True),
            *_sys(),
            _fk("tenant_id", "tenant", True),
            _fk("unit_transform_id", "mes_unit_transform", True),
            _fk("lot_id", "mes_lot"),
            _fk("wafer_id", "mes_wafer"),
            _fk("substrate_map_id", "mes_substrate_map"),
            sa.PrimaryKeyConstraint("id"),
        )
        _ix(name, "tenant_id", "unit_transform_id", "lot_id", "wafer_id",
            "substrate_map_id")
    elif name == "mes_unit_transform_output":
        op.create_table(
            name,
            *_base(),
            sa.Column("unit_transform_id", sa.Uuid(), nullable=False),
            sa.Column("lot_id", sa.Uuid(), nullable=False),
            sa.Column("product_id", sa.Uuid(), nullable=False),
            sa.Column("track_unit_kind", S(40), nullable=False),
            sa.Column("qty", I(), nullable=False),
            sa.Column("die_qty", I(), nullable=True),
            *_sys(),
            _fk("tenant_id", "tenant", True),
            _fk("unit_transform_id", "mes_unit_transform", True),
            _fk("lot_id", "mes_lot"),
            _fk("product_id", "mes_product"),
            sa.PrimaryKeyConstraint("id"),
        )
        _ix(name, "tenant_id", "unit_transform_id", "lot_id", "product_id")
    else:
        op.create_table(
            name,
            *_base(),
            sa.Column("unit_transform_id", sa.Uuid(), nullable=False),
            sa.Column("child_lot_id", sa.Uuid(), nullable=False),
            sa.Column("child_unit_id", sa.Uuid(), nullable=True),
            sa.Column("child_seq", I(), nullable=True),
            sa.Column("parent_lot_id", sa.Uuid(), nullable=False),
            sa.Column("parent_wafer_id", sa.Uuid(), nullable=True),
            sa.Column("die_row", I(), nullable=True),
            sa.Column("die_col", I(), nullable=True),
            sa.Column("qty", I(), nullable=False),
            *_sys(),
            _fk("tenant_id", "tenant", True),
            _fk("unit_transform_id", "mes_unit_transform", True),
            _fk("child_lot_id", "mes_lot"),
            _fk("child_unit_id", "mes_wafer"),
            _fk("parent_lot_id", "mes_lot"),
            _fk("parent_wafer_id", "mes_wafer"),
            sa.PrimaryKeyConstraint("id"),
        )
        _ix(name, "tenant_id", "unit_transform_id", "child_lot_id", "child_unit_id",
            "parent_lot_id", "parent_wafer_id")
    enable_rls(op, [name])


def upgrade():
    have = _tables()
    for name in ORDER:
        if name not in have:
            _create(name)


def downgrade():
    have = _tables()
    for name in reversed(ORDER):
        if name in have:
            disable_rls(op, [name])
            op.drop_table(name)
