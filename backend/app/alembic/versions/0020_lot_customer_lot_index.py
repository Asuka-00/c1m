"""D36/D37：mes_lot (tenant_id, upper(customer_lot_no)) 普通索引（客户批号不区分大小写的互查 / 追溯 / 搜索）

升级 / 降级均可重复执行。

Revision ID: 0020_lot_customer_lot_index
Revises: 0019_customer_material
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_lot_customer_lot_index"
down_revision = "0019_customer_material"
branch_labels = None
depends_on = None

T = "mes_lot"
IDX = "ix_mes_lot_customer_lot_no"


def _ready() -> bool:
    i = sa.inspect(op.get_bind())
    return T in i.get_table_names() and any(
        c["name"] == "customer_lot_no" for c in i.get_columns(T)
    )


def _has() -> bool:
    i = sa.inspect(op.get_bind())
    return T in i.get_table_names() and any(x["name"] == IDX for x in i.get_indexes(T))


def upgrade():
    if _ready() and not _has():
        op.create_index(
            IDX, T, ["tenant_id", sa.text("upper(customer_lot_no)")], unique=False
        )


def downgrade():
    if _has():
        op.drop_index(IDX, table_name=T)
