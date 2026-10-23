"""出站扣料明细 ``mes_lot_material_use``：物料批反向追溯用（替代对履历 JSON 的文本匹配）。

新建时从已有的出站履历（``details.consumed``）回填。

Revision ID: 0015_lot_material_use
Revises: 0014_bom_material_issue
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0015_lot_material_use"
down_revision = "0014_bom_material_issue"
branch_labels = None
depends_on = None

TABLE = "mes_lot_material_use"

# 履历里只记了物料批编码，按（租户，编码）找回物料批
BACKFILL = """
INSERT INTO mes_lot_material_use
    (id, tenant_id, lot_id, route_step_id, operation_id, equipment_id,
     material_lot_id, material_id, qty, uom_id, at, created_at, updated_at)
SELECT gen_random_uuid(), h.tenant_id, h.lot_id, h.route_step_id, h.operation_id,
       h.equipment_id, ml.id, ml.material_id, (c ->> 'qty')::float, ml.uom_id,
       h.at, h.at, h.at
FROM mes_lot_history h
CROSS JOIN LATERAL json_array_elements(
    CASE WHEN json_typeof(h.details -> 'consumed') = 'array'
         THEN h.details -> 'consumed' ELSE '[]'::json END
) c
JOIN mes_material_lot ml
  ON ml.tenant_id = h.tenant_id AND ml.code = c ->> 'material_lot'
WHERE h.action = 'track_out'
"""


def upgrade():
    if sa.inspect(op.get_bind()).has_table(TABLE):  # stamp 后重复升级：已存在
        return
    op.create_table(
        "mes_lot_material_use",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("lot_id", sa.Uuid(), nullable=False),
        sa.Column("route_step_id", sa.Uuid(), nullable=True),
        sa.Column("operation_id", sa.Uuid(), nullable=True),
        sa.Column("equipment_id", sa.Uuid(), nullable=True),
        sa.Column("material_lot_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("uom_id", sa.Uuid(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attrs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["equipment_id"], ["mes_equipment.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["lot_id"], ["mes_lot.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["material_id"], ["mes_material.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["material_lot_id"], ["mes_material_lot.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["mes_operation.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["route_step_id"], ["mes_route_step.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uom_id"], ["mes_uom.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mes_lot_material_use_equipment_id"),
        "mes_lot_material_use",
        ["equipment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mes_lot_material_use_lot_id"),
        "mes_lot_material_use",
        ["lot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mes_lot_material_use_material_id"),
        "mes_lot_material_use",
        ["material_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mes_lot_material_use_material_lot_id"),
        "mes_lot_material_use",
        ["material_lot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mes_lot_material_use_operation_id"),
        "mes_lot_material_use",
        ["operation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mes_lot_material_use_route_step_id"),
        "mes_lot_material_use",
        ["route_step_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mes_lot_material_use_tenant_id"),
        "mes_lot_material_use",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mes_lot_material_use_uom_id"),
        "mes_lot_material_use",
        ["uom_id"],
        unique=False,
    )
    enable_rls(op, [TABLE])
    op.execute(BACKFILL)


def downgrade():
    if sa.inspect(op.get_bind()).has_table(TABLE):
        disable_rls(op, [TABLE])
        op.drop_table(TABLE)
