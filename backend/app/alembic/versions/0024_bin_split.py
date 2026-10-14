"""B8 按 bin 拆批：子批 bin 码、事件记下 bin 定义集与版本

- mes_lot.bin_code（可空）。
- mes_unit_transform_input：bin_set_id（外键 mes_bin_set + 索引）、bin_set_version、bin_counts。
- mes_unit_transform_output.bin_code、mes_unit_origin.bin_code（可空）。
来源 / 外部事件号及部分唯一索引沿用 0022 的 mes_unit_transform（transform_type=bin_split）。
升级 / 降级均可重复执行。

Revision ID: 0024_bin_split
Revises: 0023_substrate_map_links
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_bin_split"
down_revision = "0023_substrate_map_links"
branch_labels = None
depends_on = None

IN = "mes_unit_transform_input"
COLS: list[tuple[str, str, sa.types.TypeEngine]] = [
    ("mes_lot", "bin_code", sa.String(64)),
    (IN, "bin_set_id", sa.Uuid()),
    (IN, "bin_set_version", sa.Integer()),
    (IN, "bin_counts", sa.JSON()),
    ("mes_unit_transform_output", "bin_code", sa.String(64)),
    ("mes_unit_origin", "bin_code", sa.String(64)),
]
FK = f"fk_{IN}_bin_set_id"
IX = f"ix_{IN}_bin_set_id"


def _have() -> set[tuple[str, str]]:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    return {
        (t, c["name"])
        for t in {x[0] for x in COLS}
        if t in tables
        for c in insp.get_columns(t)
    }


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    tables, have = _tables(), _have()
    for t, c, typ in COLS:
        if t not in tables or (t, c) in have:
            continue
        op.add_column(t, sa.Column(c, typ, nullable=True))
        if (t, c) == (IN, "bin_set_id"):
            op.create_foreign_key(
                FK, IN, "mes_bin_set", ["bin_set_id"], ["id"], ondelete="RESTRICT"
            )
            op.create_index(op.f(IX), IN, ["bin_set_id"], unique=False)


def downgrade():
    have = _have()
    for t, c, _typ in reversed(COLS):
        if (t, c) not in have:
            continue
        if (t, c) == (IN, "bin_set_id"):
            op.drop_index(op.f(IX), table_name=IN)
            op.drop_constraint(FK, IN, type_="foreignkey")
        op.drop_column(t, c)
