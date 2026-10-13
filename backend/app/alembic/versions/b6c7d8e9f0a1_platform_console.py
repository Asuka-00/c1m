"""platform console: menu space, tenant plan/expiry, login log, platform op log

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-10-13 11:00:00

平台管理空间：menu.space（已有菜单默认 workspace，平台菜单由 initial_data 同步）、
tenant.plan / expires_at（已有租户默认 standard / 永久）、登录日志与平台操作日志
（平台级表，不启用租户 RLS）。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

revision = 'b6c7d8e9f0a1'
down_revision = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('menu', sa.Column('space', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default='workspace'))
    op.create_index(op.f('ix_menu_space'), 'menu', ['space'], unique=False)
    op.add_column('tenant', sa.Column('plan', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default='standard'))
    op.add_column('tenant', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table('login_log',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('ip', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
    sa.Column('user_agent', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    for c in ('email', 'user_id', 'success', 'created_at'):
        op.create_index(op.f(f'ix_login_log_{c}'), 'login_log', [c], unique=False)

    op.create_table('platform_audit',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('actor_email', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('action', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('target_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('target_id', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
    sa.Column('tenant_id', sa.Uuid(), nullable=True),
    sa.Column('detail', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    for c in ('actor_id', 'action', 'tenant_id', 'created_at'):
        op.create_index(op.f(f'ix_platform_audit_{c}'), 'platform_audit', [c], unique=False)


def downgrade():
    op.drop_table('platform_audit')
    op.drop_table('login_log')
    op.drop_column('tenant', 'expires_at')
    op.drop_column('tenant', 'plan')
    op.drop_index(op.f('ix_menu_space'), table_name='menu')
    op.drop_column('menu', 'space')
