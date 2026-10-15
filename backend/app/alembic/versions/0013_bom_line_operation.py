"""bom_line: route_step_id → operation_id（bom.md §11）

明细的可选工步改为引用工序，流程改版后不受影响。原 route_step_id 有值的行按该流程步骤的
工序回填。升级 / 降级均可重复执行（降级按工序取不回具体步骤，route_step_id 留空）。

Revision ID: 0013_bom_line_operation
Revises: 0012_bom
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_bom_line_operation"
down_revision = "0012_bom"
branch_labels = None
depends_on = None

T = "mes_bom_line"


def _cols() -> set[str]:
    insp = sa.inspect(op.get_bind())
    if T not in insp.get_table_names():  # 0012 已降级：无事可做
        return set()
    return {c["name"] for c in insp.get_columns(T)}


def upgrade():
    cols = _cols()
    if not cols:
        return
    if "operation_id" not in cols:
        op.add_column(T, sa.Column("operation_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "mes_bom_line_operation_id_fkey",
            T,
            "mes_operation",
            ["operation_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(op.f(f"ix_{T}_operation_id"), T, ["operation_id"], unique=False)
    if "route_step_id" in cols:
        op.execute(
            sa.text(
                f"UPDATE {T} l SET operation_id = rs.operation_id "
                "FROM mes_route_step rs "
                "WHERE rs.id = l.route_step_id AND l.operation_id IS NULL"
            )
        )
        op.drop_index(op.f(f"ix_{T}_route_step_id"), table_name=T)
        op.drop_column(T, "route_step_id")


def downgrade():
    cols = _cols()
    if not cols:
        return
    if "route_step_id" not in cols:
        op.add_column(T, sa.Column("route_step_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "mes_bom_line_route_step_id_fkey",
            T,
            "mes_route_step",
            ["route_step_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            op.f(f"ix_{T}_route_step_id"), T, ["route_step_id"], unique=False
        )
    if "operation_id" in cols:
        op.drop_index(op.f(f"ix_{T}_operation_id"), table_name=T)
        op.drop_column(T, "operation_id")
