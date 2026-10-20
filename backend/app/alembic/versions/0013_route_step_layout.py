"""工步画布布局：``mes_route_step.layout``

流程图编辑器里节点的位置（``{x, y, ax, ay, rx, ry}``：工步节点、子路线节点、返工路线节点的坐标），
随路线版本一起复制；未保存位置的工步由前端自动布局。

Revision ID: 0013_route_step_layout
Revises: 0012_system_notes
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_route_step_layout"
down_revision = "0012_system_notes"
branch_labels = None
depends_on = None

TABLE = "mes_route_step"


def _has() -> bool:
    cols = sa.inspect(op.get_bind()).get_columns(TABLE)
    return any(c["name"] == "layout" for c in cols)


def upgrade():
    if not _has():
        op.add_column(TABLE, sa.Column("layout", sa.JSON(), nullable=True))


def downgrade():
    if _has():
        op.drop_column(TABLE, "layout")
