"""equipment_material_mount: 机台上料记录（D28, B3）

- 上料口 = (equipment_id, port_code)；部分唯一索引 uq_mes_eqp_mount_port_open
  (tenant_id, equipment_id, port_code) WHERE unmounted_at IS NULL：同一上料口同时只装一批。
- 外部事件去重：uq_mes_eqp_mount_event (tenant_id, source, external_event_id)
  WHERE external_event_id IS NOT NULL。
升级 / 降级均可重复执行。

Revision ID: 0014_equipment_material_mount
Revises: 0013_bom_line_operation
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0014_equipment_material_mount"
down_revision = "0013_bom_line_operation"
branch_labels = None
depends_on = None

T = "mes_equipment_material_mount"


def _exists() -> bool:
    return T in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if _exists():
        return
    op.create_table(
        T,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("equipment_id", sa.Uuid(), nullable=False),
        sa.Column("port_code", sa.String(length=64), nullable=False),
        sa.Column("material_lot_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=True),
        sa.Column("mounted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unmounted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("external_event_id", sa.String(length=128), nullable=True),
        sa.Column("mounted_by", sa.String(length=255), nullable=True),
        sa.Column("unmounted_by", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.String(length=300), nullable=True),
        sa.Column("attrs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["equipment_id"], ["mes_equipment.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["material_lot_id"], ["mes_material_lot.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["mes_material.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for c in ("tenant_id", "equipment_id", "material_lot_id", "material_id"):
        op.create_index(op.f(f"ix_{T}_{c}"), T, [c], unique=False)
    op.create_index(
        "uq_mes_eqp_mount_port_open",
        T,
        ["tenant_id", "equipment_id", "port_code"],
        unique=True,
        postgresql_where=sa.text("unmounted_at IS NULL"),
    )
    op.create_index(
        "uq_mes_eqp_mount_event",
        T,
        ["tenant_id", "source", "external_event_id"],
        unique=True,
        postgresql_where=sa.text("external_event_id IS NOT NULL"),
    )
    enable_rls(op, [T])


def downgrade():
    if not _exists():
        return
    disable_rls(op, [T])
    op.drop_table(T)
