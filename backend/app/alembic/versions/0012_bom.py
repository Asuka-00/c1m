"""bom: BOM / bom_line / bom_line_substitute + lot.bom_id (D28, B1)

- mes_bom：产品 BOM 版本（draft / active / superseded / void），同一产品只允许一个
  active（部分唯一索引 uq_mes_bom_active）。
- mes_bom_line：明细（物料或半成品、用量 Numeric(18,6) + 单位、per_basis、损耗率、
  扣料方式、可选流程步骤）。
- mes_bom_line_substitute：替代料（按优先级）。
- mes_lot.bom_id：开批时锁定的 BOM 版本；现有批次不迁移（为空）。

Revision ID: 0012_bom
Revises: 0011_qtime_rule_active_no_scrap
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0012_bom"
down_revision = "0011_qtime_rule_active_no_scrap"
branch_labels = None
depends_on = None

TABLES = ["mes_bom", "mes_bom_line", "mes_bom_line_substitute"]


def _sys() -> list[sa.Column]:
    return [
        sa.Column("attrs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    ]


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
    ]


def _fk(col: str, target: str, cascade: bool = False) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [col], [f"{target}.id"], ondelete="CASCADE" if cascade else "RESTRICT"
    )


def _ix(table: str, *cols: str) -> None:
    for c in cols:
        op.create_index(op.f(f"ix_{table}_{c}"), table, [c], unique=False)


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _lot_has_bom() -> bool:
    cols = sa.inspect(op.get_bind()).get_columns("mes_lot")
    return any(c["name"] == "bom_id" for c in cols)


def upgrade():
    # 可重复执行：表 / 列已存在时跳过（与 0009–0011 一致）
    if "mes_bom" not in _tables():
        _create()
    if not _lot_has_bom():
        op.add_column("mes_lot", sa.Column("bom_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "mes_lot_bom_id_fkey",
            "mes_lot",
            "mes_bom",
            ["bom_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(op.f("ix_mes_lot_bom_id"), "mes_lot", ["bom_id"], unique=False)


def _create() -> None:
    op.create_table(
        "mes_bom",
        *_base(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.String(length=255), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("copied_from_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_sys(),
        _fk("tenant_id", "tenant", cascade=True),
        _fk("product_id", "mes_product"),
        _fk("copied_from_id", "mes_bom"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "product_id",
            "version",
            name="uq_mes_bom_0",
            postgresql_nulls_not_distinct=True,
        ),
    )
    _ix("mes_bom", "tenant_id", "product_id", "copied_from_id")
    op.create_index(
        "uq_mes_bom_active",
        "mes_bom",
        ["tenant_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "mes_bom_line",
        *_base(),
        sa.Column("bom_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("component_type", sa.String(length=40), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=True),
        sa.Column("component_product_id", sa.Uuid(), nullable=True),
        sa.Column("qty", sa.Numeric(18, 6), nullable=False),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("per_basis", sa.String(length=40), nullable=False),
        sa.Column("scrap_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("consume_mode", sa.String(length=40), nullable=False),
        sa.Column("route_step_id", sa.Uuid(), nullable=True),
        sa.Column("remark", sa.String(length=300), nullable=True),
        *_sys(),
        _fk("tenant_id", "tenant", cascade=True),
        _fk("bom_id", "mes_bom", cascade=True),
        _fk("material_id", "mes_material"),
        _fk("component_product_id", "mes_product"),
        _fk("uom_id", "mes_uom"),
        _fk("route_step_id", "mes_route_step"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "bom_id",
            "line_no",
            name="uq_mes_bom_line_0",
            postgresql_nulls_not_distinct=True,
        ),
    )
    _ix(
        "mes_bom_line",
        "tenant_id",
        "bom_id",
        "material_id",
        "component_product_id",
        "uom_id",
        "route_step_id",
    )
    op.create_table(
        "mes_bom_line_substitute",
        *_base(),
        sa.Column("bom_line_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("remark", sa.String(length=300), nullable=True),
        *_sys(),
        _fk("tenant_id", "tenant", cascade=True),
        _fk("bom_line_id", "mes_bom_line", cascade=True),
        _fk("material_id", "mes_material"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "bom_line_id",
            "material_id",
            name="uq_mes_bom_line_substitute_0",
            postgresql_nulls_not_distinct=True,
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "bom_line_id",
            "priority",
            name="uq_mes_bom_line_substitute_1",
            postgresql_nulls_not_distinct=True,
        ),
    )
    _ix("mes_bom_line_substitute", "tenant_id", "bom_line_id", "material_id")
    enable_rls(op, TABLES)


def downgrade():
    if _lot_has_bom():
        op.drop_index(op.f("ix_mes_lot_bom_id"), table_name="mes_lot")
        op.drop_constraint("mes_lot_bom_id_fkey", "mes_lot", type_="foreignkey")
        op.drop_column("mes_lot", "bom_id")
    if "mes_bom" in _tables():
        disable_rls(op, TABLES)
        for t in reversed(TABLES):
            op.drop_table(t)
