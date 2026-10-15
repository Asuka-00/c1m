"""P3-B1（D79 / D89）：打标模板 ``mes_marking_template`` + 版本 ``mes_marking_template_version``。

- 模板：code（≤64，租户内唯一）、name、description、product_id / customer_id（FK RESTRICT）、creator。
- 版本：template_id（FK RESTRICT）、version（从 1 递增，(tenant, template, version) 唯一）、
  status（draft/approved/retired，D89 补充一）、lines JSON、drafter、approved_by/at、retired_at；
  部分唯一索引：每模板至多一条 draft、至多一条 approved。
- 两表租户 RLS；运行时角色权限来自 0036 的默认权限（不另行 GRANT）。

Revision ID: 0038_d79_marking_template
Revises: 0037_d74_operator_qual_log
"""

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls_sql, enable_tenant_rls_sql

revision = "0038_d79_marking_template"
down_revision = "0037_d74_operator_qual_log"
branch_labels = None
depends_on = None

T, V = "mes_marking_template", "mes_marking_template_version"
DT = sa.DateTime(timezone=True)


def _sys() -> list[sa.Column]:
    return [
        sa.Column("attrs", sa.JSON(), nullable=True),
        sa.Column("created_at", DT, nullable=True),
        sa.Column("updated_at", DT, nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    ]


def upgrade():
    names = sa.inspect(op.get_bind()).get_table_names()
    if T not in names:
        op.create_table(
            T,
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("product_id", sa.Uuid(), nullable=False),
            sa.Column("customer_id", sa.Uuid(), nullable=False),
            sa.Column("creator", sa.String(255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            *_sys(),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["product_id"], ["mes_product.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["customer_id"], ["mes_customer.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id", "code", name=f"uq_{T}_0", postgresql_nulls_not_distinct=True
            ),
            sa.UniqueConstraint(
                "tenant_id",
                "product_id",
                "customer_id",
                name=f"uq_{T}_1",
                postgresql_nulls_not_distinct=True,
            ),
        )
        for c in ("tenant_id", "product_id", "customer_id"):
            op.create_index(op.f(f"ix_{T}_{c}"), T, [c])
        for stmt in enable_tenant_rls_sql(T):
            op.execute(stmt)
    if V not in names:
        op.create_table(
            V,
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("template_id", sa.Uuid(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("lines", sa.JSON(), nullable=True),
            sa.Column("drafter", sa.String(255), nullable=True),
            sa.Column("approved_by", sa.String(255), nullable=True),
            sa.Column("approved_at", DT, nullable=True),
            sa.Column("retired_at", DT, nullable=True),
            *_sys(),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["template_id"], [f"{T}.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "template_id",
                "version",
                name=f"uq_{V}_0",
                postgresql_nulls_not_distinct=True,
            ),
        )
        op.create_index(op.f(f"ix_{V}_tenant_id"), V, ["tenant_id"])
        op.create_index(op.f(f"ix_{V}_template_id"), V, ["template_id"])
        op.create_index(
            "uq_mes_marking_template_version_open",
            V,
            ["tenant_id", "template_id"],
            unique=True,
            postgresql_where=sa.text("status = 'draft'"),
        )
        op.create_index(
            "uq_mes_marking_template_version_approved",
            V,
            ["tenant_id", "template_id"],
            unique=True,
            postgresql_where=sa.text("status = 'approved'"),
        )
        for stmt in enable_tenant_rls_sql(V):
            op.execute(stmt)


def downgrade():
    names = sa.inspect(op.get_bind()).get_table_names()
    for t in (V, T):
        if t in names:
            for stmt in disable_tenant_rls_sql(t):
                op.execute(stmt)
            op.drop_table(t)
