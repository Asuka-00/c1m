"""D74（P3-B6）：人员资质履历表 ``mes_operator_qual_log``。

- 列：qual_id（FK→mes_operator_qual，RESTRICT）、action（operator_qual_log_action）、
  before/after（JSON 快照）、reason_id（FK→mes_reason_code，RESTRICT，可空）、
  comment（≤300）、approved_by（≤64）、username、at（UTC）+ 通用系统列。
- 索引 (tenant_id, qual_id, at)；租户 RLS（ENABLE + FORCE，策略 tenant_isolation）。
- 旧数据不补履历。运行时角色的表权限来自 0036 设置的默认权限（ALTER DEFAULT
  PRIVILEGES，迁移角色建表即自动授予），本迁移不另行 GRANT（测试断言 app_user 有 DML）。
- 编号：D74 原定 0033；0033/0034 仍预留给 B6 早期草案 / B8，按 0036 之后接 0037。

Revision ID: 0037_d74_operator_qual_log
Revises: 0036_d83_runtime_role_grants
"""

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_tenant_rls_sql, enable_tenant_rls_sql

revision = "0037_d74_operator_qual_log"
down_revision = "0036_d83_runtime_role_grants"
branch_labels = None
depends_on = None

T = "mes_operator_qual_log"
DT = sa.DateTime(timezone=True)


def upgrade():
    bind = op.get_bind()
    if T not in sa.inspect(bind).get_table_names():
        op.create_table(
            T,
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("qual_id", sa.Uuid(), nullable=False),
            sa.Column("action", sa.String(40), nullable=False),
            sa.Column("before", sa.JSON(), nullable=True),
            sa.Column("after", sa.JSON(), nullable=True),
            sa.Column("reason_id", sa.Uuid(), nullable=True),
            sa.Column("comment", sa.String(300), nullable=True),
            sa.Column("approved_by", sa.String(64), nullable=True),
            sa.Column("username", sa.String(255), nullable=True),
            sa.Column("at", DT, nullable=False),
            sa.Column("attrs", sa.JSON(), nullable=True),
            sa.Column("created_at", DT, nullable=True),
            sa.Column("updated_at", DT, nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["qual_id"], ["mes_operator_qual.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["reason_id"], ["mes_reason_code.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        for c in ("tenant_id", "qual_id", "reason_id"):
            op.create_index(op.f(f"ix_{T}_{c}"), T, [c], unique=False)
        op.create_index(
            "ix_mes_operator_qual_log_qual_at", T, ["tenant_id", "qual_id", "at"]
        )
        for stmt in enable_tenant_rls_sql(T):
            op.execute(stmt)


def downgrade():
    if T in sa.inspect(op.get_bind()).get_table_names():
        for stmt in disable_tenant_rls_sql(T):
            op.execute(stmt)
        op.drop_table(T)
