"""B7 客户来料 + equipment_qual 子单元改名（D35）

- 新表 mes_customer（客户主数据：code / name / short_name / description）。
- mes_lot：customer_lot_no（String 100）、ownership（String 40，默认 own）、customer_id（→ mes_customer）。
- mes_material_lot：ownership（默认 own）、customer_id（→ mes_customer）。
  现有数据 ownership 回填 own，客户字段为空。
- mes_equipment_qual.chamber_id 改名为 sub_unit_id（设备任意子单元：腔体 / 主轴 / 测试头 /
  焊头），外键与索引一并改名；仍可空，本期不建子单元表（引用 mes_equipment 子设备）。
升级 / 降级均可重复执行。

Revision ID: 0019_customer_material
Revises: 0018_equipment_qual_source
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0019_customer_material"
down_revision = "0018_equipment_qual_source"
branch_labels = None
depends_on = None

CUST = "mes_customer"
LOT = "mes_lot"
ML = "mes_material_lot"
Q = "mes_equipment_qual"
OLD_FK = "fk_mes_equipment_qual_chamber_id"
NEW_FK = "fk_mes_equipment_qual_sub_unit_id"


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_insp().get_table_names())


def _cols(t: str) -> set[str]:
    return {c["name"] for c in _insp().get_columns(t)} if t in _tables() else set()


def _idx(t: str) -> set[str]:
    return {i["name"] for i in _insp().get_indexes(t)} if t in _tables() else set()


def _fks(t: str) -> set[str]:
    return {f["name"] for f in _insp().get_foreign_keys(t)} if t in _tables() else set()


def _add_customer_cols(t: str, with_lot_no: bool) -> None:
    if t not in _tables():
        return
    cols = _cols(t)
    if with_lot_no and "customer_lot_no" not in cols:
        op.add_column(t, sa.Column("customer_lot_no", sa.String(length=100)))
    if "ownership" not in cols:
        op.add_column(
            t, sa.Column("ownership", sa.String(length=40), server_default="own")
        )
        op.alter_column(t, "ownership", server_default=None)
    if "customer_id" not in cols:
        op.add_column(t, sa.Column("customer_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"{t}_customer_id_fkey", t, CUST, ["customer_id"], ["id"], ondelete="RESTRICT"
        )
    if f"ix_{t}_customer_id" not in _idx(t):
        op.create_index(op.f(f"ix_{t}_customer_id"), t, ["customer_id"], unique=False)


def _drop_customer_cols(t: str) -> None:
    if t not in _tables():
        return
    if f"ix_{t}_customer_id" in _idx(t):
        op.drop_index(op.f(f"ix_{t}_customer_id"), table_name=t)
    cols = _cols(t)
    for c in ("customer_id", "ownership", "customer_lot_no"):
        if c in cols:
            op.drop_column(t, c)  # 外键随列删除


def _rename_sub_unit(old: str, new: str, old_fk: str, new_fk: str) -> None:
    cols = _cols(Q)
    if old not in cols or new in cols:
        return
    if old_fk in _fks(Q):
        op.drop_constraint(old_fk, Q, type_="foreignkey")
    if f"ix_{Q}_{old}" in _idx(Q):
        op.drop_index(op.f(f"ix_{Q}_{old}"), table_name=Q)
    op.alter_column(Q, old, new_column_name=new)
    op.create_foreign_key(new_fk, Q, "mes_equipment", [new], ["id"], ondelete="RESTRICT")
    op.create_index(op.f(f"ix_{Q}_{new}"), Q, [new], unique=False)


def upgrade():
    if CUST not in _tables():
        op.create_table(
            CUST,
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("short_name", sa.String(length=50), nullable=True),
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
                name="uq_mes_customer_0",
                postgresql_nulls_not_distinct=True,
            ),
        )
        op.create_index(op.f(f"ix_{CUST}_tenant_id"), CUST, ["tenant_id"], unique=False)
        enable_rls(op, [CUST])
    _add_customer_cols(LOT, True)
    _add_customer_cols(ML, False)
    _rename_sub_unit("chamber_id", "sub_unit_id", OLD_FK, NEW_FK)


def downgrade():
    _rename_sub_unit("sub_unit_id", "chamber_id", NEW_FK, OLD_FK)
    _drop_customer_cols(ML)
    _drop_customer_cols(LOT)
    if CUST in _tables():
        disable_rls(op, [CUST])
        op.drop_table(CUST)
