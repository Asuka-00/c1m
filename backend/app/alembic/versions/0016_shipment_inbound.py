"""出货单与来料接收单：``mes_shipment`` / ``mes_shipment_line`` / ``mes_material_receipt`` /
``mes_material_receipt_line``，以及 ``mes_lot.shipped_qty``、``mes_material_lot.supplier_lot``。

Revision ID: 0016_shipment_inbound
Revises: 0015_lot_material_use
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0016_shipment_inbound"
down_revision = "0015_lot_material_use"
branch_labels = None
depends_on = None

TABLES = [
    "mes_shipment",
    "mes_shipment_line",
    "mes_material_receipt",
    "mes_material_receipt_line",
]
COLUMNS = [
    ("mes_lot", sa.Column("shipped_qty", sa.Integer(), nullable=True)),
    (
        "mes_material_lot",
        sa.Column("supplier_lot", sa.String(length=100), nullable=True),
    ),
]


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_col(table: str, col: str) -> bool:
    return any(c["name"] == col for c in sa.inspect(op.get_bind()).get_columns(table))


def upgrade():
    if not _has_table(TABLES[0]):  # stamp 后重复升级：表已存在
        op.create_table(
            "mes_shipment",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("customer", sa.String(length=200), nullable=False),
            sa.Column("warehouse_id", sa.Uuid(), nullable=True),
            sa.Column("waybill", sa.String(length=100), nullable=True),
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
                ["warehouse_id"], ["mes_warehouse.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "code",
                name="uq_mes_shipment_0",
                postgresql_nulls_not_distinct=True,
            ),
        )
        op.create_index(
            op.f("ix_mes_shipment_tenant_id"),
            "mes_shipment",
            ["tenant_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_shipment_warehouse_id"),
            "mes_shipment",
            ["warehouse_id"],
            unique=False,
        )
        op.create_table(
            "mes_shipment_line",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("shipment_id", sa.Uuid(), nullable=False),
            sa.Column("lot_id", sa.Uuid(), nullable=False),
            sa.Column("product_id", sa.Uuid(), nullable=True),
            sa.Column("qty", sa.Integer(), nullable=False),
            sa.Column("attrs", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(["lot_id"], ["mes_lot.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["product_id"], ["mes_product.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["shipment_id"], ["mes_shipment.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "shipment_id",
                "lot_id",
                name="uq_mes_shipment_line_0",
                postgresql_nulls_not_distinct=True,
            ),
        )
        op.create_index(
            op.f("ix_mes_shipment_line_lot_id"),
            "mes_shipment_line",
            ["lot_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_shipment_line_product_id"),
            "mes_shipment_line",
            ["product_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_shipment_line_shipment_id"),
            "mes_shipment_line",
            ["shipment_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_shipment_line_tenant_id"),
            "mes_shipment_line",
            ["tenant_id"],
            unique=False,
        )
        op.create_table(
            "mes_material_receipt",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("supplier", sa.String(length=200), nullable=False),
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
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "code",
                name="uq_mes_material_receipt_0",
                postgresql_nulls_not_distinct=True,
            ),
        )
        op.create_index(
            op.f("ix_mes_material_receipt_tenant_id"),
            "mes_material_receipt",
            ["tenant_id"],
            unique=False,
        )
        op.create_table(
            "mes_material_receipt_line",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("material_receipt_id", sa.Uuid(), nullable=False),
            sa.Column("material_id", sa.Uuid(), nullable=False),
            sa.Column("qty", sa.Float(), nullable=False),
            sa.Column("uom_id", sa.Uuid(), nullable=False),
            sa.Column("supplier_lot", sa.String(length=100), nullable=True),
            sa.Column("expiry_date", sa.Date(), nullable=True),
            sa.Column("location", sa.String(length=100), nullable=True),
            sa.Column("iqc_result", sa.String(length=40), nullable=True),
            sa.Column("material_lot_id", sa.Uuid(), nullable=True),
            sa.Column("attrs", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(
                ["material_id"], ["mes_material.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["material_lot_id"], ["mes_material_lot.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["material_receipt_id"], ["mes_material_receipt.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["uom_id"], ["mes_uom.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_mes_material_receipt_line_material_id"),
            "mes_material_receipt_line",
            ["material_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_material_receipt_line_material_lot_id"),
            "mes_material_receipt_line",
            ["material_lot_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_material_receipt_line_material_receipt_id"),
            "mes_material_receipt_line",
            ["material_receipt_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_material_receipt_line_tenant_id"),
            "mes_material_receipt_line",
            ["tenant_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_mes_material_receipt_line_uom_id"),
            "mes_material_receipt_line",
            ["uom_id"],
            unique=False,
        )
        enable_rls(op, TABLES)
    for table, col in COLUMNS:
        if not _has_col(table, col.name):
            op.add_column(table, col)


def downgrade():
    for table, col in reversed(COLUMNS):
        if _has_col(table, col.name):
            op.drop_column(table, col.name)
    present = [t for t in TABLES if _has_table(t)]
    disable_rls(op, present)
    for t in reversed(present):
        op.drop_table(t)
