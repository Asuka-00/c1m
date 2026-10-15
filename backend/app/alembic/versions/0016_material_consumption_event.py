"""material_consumption.external_event_id + 部分唯一索引（D28, B2 补充）

- 新增可空列 external_event_id（String 128）。
- 部分唯一索引 uq_mes_mat_consumption_event (tenant_id, source, external_event_id)
  WHERE external_event_id IS NOT NULL：同一来源同一外部事件号只记一次（写法同上料表）。
升级 / 降级均可重复执行。

Revision ID: 0016_material_consumption_event
Revises: 0015_material_consumption
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_material_consumption_event"
down_revision = "0015_material_consumption"
branch_labels = None
depends_on = None

T = "mes_material_consumption"
COL = "external_event_id"
IDX = "uq_mes_mat_consumption_event"


def _has_table() -> bool:
    return T in sa.inspect(op.get_bind()).get_table_names()


def _cols() -> set[str]:
    if not _has_table():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(T)}


def _idx() -> set[str]:
    if not _has_table():
        return set()
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(T)}


def upgrade():
    if not _has_table():  # 0015 未建表（不应发生）：跳过
        return
    if COL not in _cols():
        op.add_column(T, sa.Column(COL, sa.String(length=128), nullable=True))
    if IDX not in _idx():
        op.create_index(
            IDX,
            T,
            ["tenant_id", "source", COL],
            unique=True,
            postgresql_where=sa.text("external_event_id IS NOT NULL"),
        )


def downgrade():
    if IDX in _idx():
        op.drop_index(IDX, table_name=T)
    if COL in _cols():
        op.drop_column(T, COL)
