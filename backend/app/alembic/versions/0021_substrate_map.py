"""B4 坐标图：map_import / bin_set / bin_definition / substrate_map / map_cell

- mes_map_import：导入记录，source（manual/eap，非空）、external_event_id（可空），
  部分唯一索引 uq_mes_map_import_event (tenant_id, source, external_event_id)
  WHERE external_event_id IS NOT NULL（写法同上料表）。
- mes_bin_set（定义集 + 版本，唯一 (tenant, code, version)）、mes_bin_definition（bin 码、bin_type）。
- mes_substrate_map（基板编号 + map_version 唯一；原点 / 轴向取自文件头；引用定义集与导入记录；
  total / good / excluded 数量与各 bin 数量）、mes_map_cell（(map, row, col) 唯一）。
升级 / 降级均可重复执行。

Revision ID: 0021_substrate_map
Revises: 0020_lot_customer_lot_index
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0021_substrate_map"
down_revision = "0020_lot_customer_lot_index"
branch_labels = None
depends_on = None

ORDER = [
    "mes_map_import",
    "mes_bin_set",
    "mes_bin_definition",
    "mes_substrate_map",
    "mes_map_cell",
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


def _uq(name: str, *cols: str) -> sa.UniqueConstraint:
    return sa.UniqueConstraint(
        "tenant_id", *cols, name=name, postgresql_nulls_not_distinct=True
    )


def _create(name: str) -> None:
    S = sa.String
    if name == "mes_map_import":
        op.create_table(
            name,
            *_base(),
            sa.Column("import_kind", S(40), nullable=False),
            sa.Column("source", S(40), nullable=False),
            sa.Column("external_event_id", S(128), nullable=True),
            sa.Column("file_name", S(255), nullable=True),
            sa.Column("row_count", sa.Integer(), nullable=True),
            sa.Column("imported_by", S(255), nullable=True),
            sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
            *_sys(),
            _fk("tenant_id", "tenant", True),
            sa.PrimaryKeyConstraint("id"),
        )
        _ix(name, "tenant_id")
        op.create_index(
            "uq_mes_map_import_event",
            name,
            ["tenant_id", "source", "external_event_id"],
            unique=True,
            postgresql_where=sa.text("external_event_id IS NOT NULL"),
        )
    elif name == "mes_bin_set":
        op.create_table(
            name,
            *_base(),
            sa.Column("code", S(64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("map_import_id", sa.Uuid(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            *_sys(),
            _fk("tenant_id", "tenant", True),
            _fk("map_import_id", "mes_map_import"),
            sa.PrimaryKeyConstraint("id"),
            _uq("uq_mes_bin_set_0", "code", "version"),
        )
        _ix(name, "tenant_id", "map_import_id")
    elif name == "mes_bin_definition":
        op.create_table(
            name,
            *_base(),
            sa.Column("bin_set_id", sa.Uuid(), nullable=False),
            sa.Column("bin_code", S(32), nullable=False),
            sa.Column("bin_type", S(40), nullable=False),
            sa.Column("description", S(200), nullable=True),
            *_sys(),
            _fk("tenant_id", "tenant", True),
            _fk("bin_set_id", "mes_bin_set", True),
            sa.PrimaryKeyConstraint("id"),
            _uq("uq_mes_bin_definition_0", "bin_set_id", "bin_code"),
        )
        _ix(name, "tenant_id", "bin_set_id")
    elif name == "mes_substrate_map":
        op.create_table(
            name,
            *_base(),
            sa.Column("code", S(64), nullable=False),
            sa.Column("substrate_type", S(40), nullable=False),
            sa.Column("map_version", sa.Integer(), nullable=False),
            sa.Column("rows", sa.Integer(), nullable=False),
            sa.Column("cols", sa.Integer(), nullable=False),
            sa.Column("origin_location", S(40), nullable=False),
            sa.Column("x_axis", S(40), nullable=False),
            sa.Column("y_axis", S(40), nullable=False),
            sa.Column("bin_set_id", sa.Uuid(), nullable=False),
            sa.Column("map_import_id", sa.Uuid(), nullable=False),
            sa.Column("total_qty", sa.Integer(), nullable=False),
            sa.Column("good_qty", sa.Integer(), nullable=True),
            sa.Column("excluded_qty", sa.Integer(), nullable=True),
            sa.Column("bin_counts", sa.JSON(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            *_sys(),
            _fk("tenant_id", "tenant", True),
            _fk("bin_set_id", "mes_bin_set"),
            _fk("map_import_id", "mes_map_import"),
            sa.PrimaryKeyConstraint("id"),
            _uq("uq_mes_substrate_map_0", "code", "map_version"),
        )
        _ix(name, "tenant_id", "bin_set_id", "map_import_id")
    else:
        op.create_table(
            name,
            *_base(),
            sa.Column("substrate_map_id", sa.Uuid(), nullable=False),
            sa.Column("row", sa.Integer(), nullable=False),
            sa.Column("col", sa.Integer(), nullable=False),
            sa.Column("bin_code", S(32), nullable=False),
            *_sys(),
            _fk("tenant_id", "tenant", True),
            _fk("substrate_map_id", "mes_substrate_map", True),
            sa.PrimaryKeyConstraint("id"),
            _uq("uq_mes_map_cell_0", "substrate_map_id", "row", "col"),
        )
        _ix(name, "tenant_id", "substrate_map_id")
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
