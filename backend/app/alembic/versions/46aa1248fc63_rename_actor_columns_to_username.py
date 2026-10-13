"""rename actor columns to username

操作人字段改名为基于用户名的列名（值在 389542902fa8 中已转换为用户名）：
- 各审计 / 履历表 ``user_email`` → ``username``
- ``platform_audit.actor_email`` → ``actor_username``
- ``login_log.email`` → ``username``（索引同步改名）

Revision ID: 46aa1248fc63
Revises: 389542902fa8
Create Date: 2026-10-13
"""

from alembic import op

revision = "46aa1248fc63"
down_revision = "389542902fa8"
branch_labels = None
depends_on = None

USER_EMAIL_TABLES = (
    "mes_audit_log",
    "mes_check_log",
    "mes_dc_result",
    "mes_e10_history",
    "mes_lot_genealogy",
    "mes_lot_history",
    "mes_pm_record",
)


def upgrade():
    for t in USER_EMAIL_TABLES:
        op.alter_column(t, "user_email", new_column_name="username")
    op.alter_column("platform_audit", "actor_email", new_column_name="actor_username")
    op.alter_column("login_log", "email", new_column_name="username")
    op.execute("ALTER INDEX ix_login_log_email RENAME TO ix_login_log_username")


def downgrade():
    op.execute("ALTER INDEX ix_login_log_username RENAME TO ix_login_log_email")
    op.alter_column("login_log", "username", new_column_name="email")
    op.alter_column("platform_audit", "actor_username", new_column_name="actor_email")
    for t in USER_EMAIL_TABLES:
        op.alter_column(t, "username", new_column_name="user_email")
