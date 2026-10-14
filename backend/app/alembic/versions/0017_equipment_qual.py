"""PM 后 Qual 放行（B6）：equipment.qual_state + equipment_qual（Qual 任务）

- mes_equipment.qual_state（String 40，可空；空视为 ready）：PM 判 OK 后为 wait_qual（WAIT_QUAL）。
- mes_equipment_qual：Qual 任务（equipment、pm_plan、pm_record、qual_status open/passed/failed、
  retry_of、requested_at、done_by、done_at、comment）；时间均为 timestamptz。
升级 / 降级均可重复执行。

Revision ID: 0017_equipment_qual
Revises: 0016_material_consumption_event
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0017_equipment_qual"
down_revision = "0016_material_consumption_event"
branch_labels = None
depends_on = None

T = "mes_equipment_qual"
EQ = "mes_equipment"


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_col() -> bool:
    return any(c["name"] == "qual_state" for c in _insp().get_columns(EQ))


def upgrade():
    if not _has_col():
        op.add_column(EQ, sa.Column("qual_state", sa.String(length=40), nullable=True))
    if T in _insp().get_table_names():
        return
    op.create_table(
        T,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("equipment_id", sa.Uuid(), nullable=False),
        sa.Column("pm_plan_id", sa.Uuid(), nullable=True),
        sa.Column("pm_record_id", sa.Uuid(), nullable=True),
        sa.Column("qual_status", sa.String(length=40), nullable=True),
        sa.Column("retry_of_id", sa.Uuid(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_by", sa.String(length=255), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.String(length=300), nullable=True),
        sa.Column("attrs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["equipment_id"], ["mes_equipment.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["pm_plan_id"], ["mes_pm_plan.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["pm_record_id"], ["mes_pm_record.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["retry_of_id"], ["mes_equipment_qual.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for c in ("tenant_id", "equipment_id", "pm_plan_id", "pm_record_id", "retry_of_id"):
        op.create_index(op.f(f"ix_{T}_{c}"), T, [c], unique=False)
    enable_rls(op, [T])


def downgrade():
    if T in _insp().get_table_names():
        disable_rls(op, [T])
        op.drop_table(T)
    if EQ in _insp().get_table_names() and _has_col():
        op.drop_column(EQ, "qual_state")
