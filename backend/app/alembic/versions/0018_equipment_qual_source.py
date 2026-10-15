"""equipment_qual：source / external_event_id / chamber_id + 部分唯一索引（B6 补充）

- source（String 40，非空，默认 manual）、external_event_id（String 128，可空）、
  chamber_id（引用 mes_equipment 子单元 / 腔体，可空）；本期人工登记不开放这三个字段。
- 部分唯一索引 uq_mes_eqp_qual_event (tenant_id, source, external_event_id)
  WHERE external_event_id IS NOT NULL（写法同上料表）。
升级 / 降级均可重复执行。

Revision ID: 0018_equipment_qual_source
Revises: 0017_equipment_qual
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_equipment_qual_source"
down_revision = "0017_equipment_qual"
branch_labels = None
depends_on = None

T = "mes_equipment_qual"
IDX = "uq_mes_eqp_qual_event"
FK = "fk_mes_equipment_qual_chamber_id"


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table() -> bool:
    return T in _insp().get_table_names()


def _cols() -> set[str]:
    return {c["name"] for c in _insp().get_columns(T)} if _has_table() else set()


def _idx() -> set[str]:
    return {i["name"] for i in _insp().get_indexes(T)} if _has_table() else set()


def upgrade():
    if not _has_table():
        return
    cols = _cols()
    if "source" not in cols:
        op.add_column(
            T,
            sa.Column(
                "source", sa.String(length=40), nullable=False, server_default="manual"
            ),
        )
        op.alter_column(T, "source", server_default=None)
    if "external_event_id" not in cols:
        op.add_column(T, sa.Column("external_event_id", sa.String(length=128)))
    # 0019 已把 chamber_id 改名为 sub_unit_id：重复执行时不再补回旧列
    if "chamber_id" not in cols and "sub_unit_id" not in cols:
        op.add_column(T, sa.Column("chamber_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            FK, T, "mes_equipment", ["chamber_id"], ["id"], ondelete="RESTRICT"
        )
    idx = _idx()
    if "chamber_id" in _cols() and f"ix_{T}_chamber_id" not in idx:
        op.create_index(op.f(f"ix_{T}_chamber_id"), T, ["chamber_id"], unique=False)
    if IDX not in idx:
        op.create_index(
            IDX,
            T,
            ["tenant_id", "source", "external_event_id"],
            unique=True,
            postgresql_where=sa.text("external_event_id IS NOT NULL"),
        )


def downgrade():
    if not _has_table():
        return
    idx = _idx()
    if IDX in idx:
        op.drop_index(IDX, table_name=T)
    if f"ix_{T}_chamber_id" in idx:
        op.drop_index(op.f(f"ix_{T}_chamber_id"), table_name=T)
    cols = _cols()
    if "chamber_id" in cols:
        op.drop_column(T, "chamber_id")  # 外键随列删除
    for c in ("external_event_id", "source"):
        if c in cols:
            op.drop_column(T, c)
