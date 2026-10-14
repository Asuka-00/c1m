"""D39 坐标图关联批次 / 设备 / 工序

mes_substrate_map 加可空 lot_id / equipment_id / operation_id（外键 RESTRICT + 索引）。
升级 / 降级均可重复执行。

Revision ID: 0023_substrate_map_links
Revises: 0022_unit_transform
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_substrate_map_links"
down_revision = "0022_unit_transform"
branch_labels = None
depends_on = None

T = "mes_substrate_map"
COLS = {"lot_id": "mes_lot", "equipment_id": "mes_equipment", "operation_id": "mes_operation"}


def _cols() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(T)}


def upgrade():
    if T not in sa.inspect(op.get_bind()).get_table_names():
        return
    have = _cols()
    for col, target in COLS.items():
        if col in have:
            continue
        op.add_column(T, sa.Column(col, sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{T}_{col}", T, target, [col], ["id"], ondelete="RESTRICT"
        )
        op.create_index(op.f(f"ix_{T}_{col}"), T, [col], unique=False)


def downgrade():
    if T not in sa.inspect(op.get_bind()).get_table_names():
        return
    have = _cols()
    for col in reversed(list(COLS)):
        if col not in have:
            continue
        op.drop_index(op.f(f"ix_{T}_{col}"), table_name=T)
        op.drop_constraint(f"fk_{T}_{col}", T, type_="foreignkey")
        op.drop_column(T, col)
