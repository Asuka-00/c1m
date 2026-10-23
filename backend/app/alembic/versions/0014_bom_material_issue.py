"""BOM、领料单、机台上料：``mes_bom`` / ``mes_bom_line`` / ``mes_material_issue`` /
``mes_material_issue_line`` / ``mes_equipment_material_mount``，
以及 ``mes_work_order.bom_id``（下达时锁定的 BOM）、``mes_material_lot.work_order_id``（领料归属工单）。

Revision ID: 0014_bom_material_issue
Revises: 0013_route_step_layout
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0014_bom_material_issue"
down_revision = "0013_route_step_layout"
branch_labels = None
depends_on = None

COLUMNS = [
    ("mes_work_order", "bom_id", "mes_bom"),
    ("mes_material_lot", "work_order_id", "mes_work_order"),
]
TABLES = [
    "mes_bom",
    "mes_bom_line",
    "mes_material_issue",
    "mes_material_issue_line",
    "mes_equipment_material_mount",
]


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_col(table: str, col: str) -> bool:
    return any(c["name"] == col for c in sa.inspect(op.get_bind()).get_columns(table))


def upgrade():
    if not _has_table("mes_bom"):  # 重复执行（stamp 后再升级）时表已存在
        op.create_table(
            "mes_bom",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("product_id", sa.Uuid(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("version", sa.Integer(), server_default="1", nullable=False),
            sa.Column(
                "status", sa.String(length=20), server_default="draft", nullable=False
            ),
            sa.Column("attrs", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(
                ["product_id"], ["mes_product.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "code",
                "version",
                name="uq_mes_bom_0",
                postgresql_nulls_not_distinct=True,
            ),
        )
        op.create_index(
            op.f("ix_mes_bom_product_id"), "mes_bom", ["product_id"], unique=False
        )
        op.create_index(
            op.f("ix_mes_bom_tenant_id"), "mes_bom", ["tenant_id"], unique=False
        )
        op.create_table(
            "mes_bom_line",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("bom_id", sa.Uuid(), nullable=False),
            sa.Column("operation_id", sa.Uuid(), nullable=False),
            sa.Column("material_id", sa.Uuid(), nullable=False),
            sa.Column("qty", sa.Float(), nullable=False),
            sa.Column("uom_id", sa.Uuid(), nullable=False),
            sa.Column("qty_basis", sa.String(length=40), nullable=True),
            sa.Column("scrap_rate", sa.Float(), nullable=True),
            sa.Column("attrs", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(["bom_id"], ["mes_bom.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["material_id"], ["mes_material.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["operation_id"], ["mes_operation.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["uom_id"], ["mes_uom.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "bom_id",
                "operation_id",
                "material_id",
                name="uq_mes_bom_line_0",
                postgresql_nulls_not_distinct=True,
            ),
        )
        op.create_index(
            op.f("ix_mes_bom_line_bom_id"), "mes_bom_line", ["bom_id"], unique=False
        )
        op.create_index(
            op.f("ix_mes_bom_line_material_id"),
            "mes_bom_line",
            ["material_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_bom_line_operation_id"),
            "mes_bom_line",
            ["operation_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_bom_line_tenant_id"),
            "mes_bom_line",
            ["tenant_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_bom_line_uom_id"), "mes_bom_line", ["uom_id"], unique=False
        )
        op.create_table(
            "mes_material_issue",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("work_order_id", sa.Uuid(), nullable=False),
            sa.Column("issue_status", sa.String(length=40), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirmed_by", sa.String(length=100), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("attrs", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["work_order_id"], ["mes_work_order.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "code",
                name="uq_mes_material_issue_0",
                postgresql_nulls_not_distinct=True,
            ),
        )
        op.create_index(
            op.f("ix_mes_material_issue_tenant_id"),
            "mes_material_issue",
            ["tenant_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_material_issue_work_order_id"),
            "mes_material_issue",
            ["work_order_id"],
            unique=False,
        )
        op.create_table(
            "mes_material_issue_line",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("material_issue_id", sa.Uuid(), nullable=False),
            sa.Column("material_lot_id", sa.Uuid(), nullable=False),
            sa.Column("qty", sa.Float(), nullable=False),
            sa.Column("attrs", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(
                ["material_issue_id"], ["mes_material_issue.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["material_lot_id"], ["mes_material_lot.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "material_issue_id",
                "material_lot_id",
                name="uq_mes_material_issue_line_0",
                postgresql_nulls_not_distinct=True,
            ),
        )
        op.create_index(
            op.f("ix_mes_material_issue_line_material_issue_id"),
            "mes_material_issue_line",
            ["material_issue_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_material_issue_line_material_lot_id"),
            "mes_material_issue_line",
            ["material_lot_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_material_issue_line_tenant_id"),
            "mes_material_issue_line",
            ["tenant_id"],
            unique=False,
        )
        op.create_table(
            "mes_equipment_material_mount",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("equipment_id", sa.Uuid(), nullable=False),
            sa.Column("position", sa.String(length=50), nullable=False),
            sa.Column("material_lot_id", sa.Uuid(), nullable=False),
            sa.Column("mounted_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("unmounted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attrs", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(
                ["equipment_id"], ["mes_equipment.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["material_lot_id"], ["mes_material_lot.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_mes_equipment_material_mount_equipment_id"),
            "mes_equipment_material_mount",
            ["equipment_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_equipment_material_mount_material_lot_id"),
            "mes_equipment_material_mount",
            ["material_lot_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_equipment_material_mount_tenant_id"),
            "mes_equipment_material_mount",
            ["tenant_id"],
            unique=False,
        )
        enable_rls(op, TABLES)
    # (表, 列, 引用表) —— 列已存在时跳过，保证 stamp 后重复升级不报错
    for table, col, target in COLUMNS:
        if _has_col(table, col):
            continue
        op.add_column(table, sa.Column(col, sa.Uuid(), nullable=True))
        op.create_index(op.f(f"ix_{table}_{col}"), table, [col])
        op.create_foreign_key(
            f"fk_{table}_{col}", table, target, [col], ["id"], ondelete="RESTRICT"
        )


def downgrade():
    for table, col, _ in reversed(COLUMNS):
        if _has_col(table, col):
            op.drop_constraint(f"fk_{table}_{col}", table, type_="foreignkey")
            op.drop_index(op.f(f"ix_{table}_{col}"), table_name=table)
            op.drop_column(table, col)
    present = [t for t in TABLES if _has_table(t)]
    disable_rls(op, present)
    for t in reversed(present):
        op.drop_table(t)
