"""material_consumption 用料记录 + 数量字段定点化（D28, B2）

- 新表 mes_material_consumption：Track Out 扣料逐条记录（来源 source、用途 usage_type），
  BOM 出站比对按工序累计 usage_type=normal 的用量。
- 数量统一 Numeric(18,6)（bom.md §10）：mes_material_lot.qty_remaining / initial_qty、
  mes_step_resource.qty 由 Float 改为 Numeric(18,6)（按 6 位四舍五入）。
升级 / 降级均可重复执行。

Revision ID: 0015_material_consumption
Revises: 0014_equipment_material_mount
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0015_material_consumption"
down_revision = "0014_equipment_material_mount"
branch_labels = None
depends_on = None

T = "mes_material_consumption"
QTY_COLS = [
    ("mes_material_lot", "qty_remaining"),
    ("mes_material_lot", "initial_qty"),
    ("mes_step_resource", "qty"),
]


def _tables() -> list[str]:
    return sa.inspect(op.get_bind()).get_table_names()


def _is_numeric(table: str, col: str) -> bool:
    for c in sa.inspect(op.get_bind()).get_columns(table):
        if c["name"] == col:
            return isinstance(c["type"], sa.Numeric) and not isinstance(
                c["type"], sa.Float
            )
    return False


def upgrade():
    for table, col in QTY_COLS:
        if not _is_numeric(table, col):
            op.alter_column(
                table,
                col,
                type_=sa.Numeric(18, 6),
                postgresql_using=f"round({col}::numeric, 6)",
            )
    if T in _tables():
        return
    op.create_table(
        T,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("lot_id", sa.Uuid(), nullable=False),
        sa.Column("route_step_id", sa.Uuid(), nullable=True),
        sa.Column("operation_id", sa.Uuid(), nullable=True),
        sa.Column("material_id", sa.Uuid(), nullable=True),
        sa.Column("material_lot_id", sa.Uuid(), nullable=True),
        sa.Column("qty", sa.Numeric(18, 6), nullable=True),
        sa.Column("uom_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("usage_type", sa.String(length=40), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attrs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lot_id"], ["mes_lot.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["route_step_id"], ["mes_route_step.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["mes_operation.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["mes_material.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["material_lot_id"], ["mes_material_lot.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["uom_id"], ["mes_uom.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for c in (
        "tenant_id",
        "lot_id",
        "route_step_id",
        "operation_id",
        "material_id",
        "material_lot_id",
        "uom_id",
    ):
        op.create_index(op.f(f"ix_{T}_{c}"), T, [c], unique=False)
    enable_rls(op, [T])


def downgrade():
    if T in _tables():
        disable_rls(op, [T])
        op.drop_table(T)
    for table, col in QTY_COLS:
        if _is_numeric(table, col):
            op.alter_column(
                table,
                col,
                type_=sa.Float(),
                postgresql_using=f"{col}::double precision",
            )
