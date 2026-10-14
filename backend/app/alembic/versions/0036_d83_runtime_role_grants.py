"""D83：迁移内给运行时角色授权，库只靠 ``alembic upgrade head`` 即可被应用使用。

背景：表级 GRANT 与 ``ALTER DEFAULT PRIVILEGES``（``pg_default_acl``）都是**库级**的。
过去授权只由 ``scripts/setup_db_roles.py`` 做，全新库只跑迁移时运行时角色对任何表都没有
权限，登录查 ``user`` 表即 ``permission denied`` → 500。该脚本还会改共用角色的密码，D83
起不再运行它。

本迁移（幂等，可重复执行）：

- 运行时角色名取 ``settings.DATABASE_URL`` 的 username，不硬编码；与迁移角色相同
  （未分离）时跳过并记日志。
- 角色不存在：**跳过并记 WARNING**（不建角色、不改密码）。选跳过而非报错，是为了不让
  没有运行时角色的环境（如只用 owner 的单机部署）无法升级。DBA 建好角色后执行
  ``alembic downgrade 0035_d80_reticle_source_unmount && alembic upgrade head`` 补授权
  （downgrade 只撤默认权限，安全）。
- GRANT CONNECT ON DATABASE <当前库>、USAGE ON SCHEMA public、表 DML、序列 USAGE/SELECT；
  ALTER DEFAULT PRIVILEGES IN SCHEMA public（表 DML、序列 USAGE/SELECT，作用于迁移角色
  以后建的对象）；alembic_version 先 REVOKE ALL 再只给 SELECT。

downgrade：只撤销本迁移设置的 default privileges，已授予的表 / 序列 / 库 / schema 权限
保留——撤掉会让正在运行的应用立刻无法访问数据，而降到 0035 的库仍需要这些权限才能用
（0035 及以前的库原本靠 setup_db_roles.py 给同样的权限）。

Revision ID: 0036_d83_runtime_role_grants
Revises: 0035_d80_reticle_source_unmount
"""

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import make_url

from app.core.config import settings

revision = "0036_d83_runtime_role_grants"
down_revision = "0035_d80_reticle_source_unmount"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

TABLE_PRIVS = "SELECT, INSERT, UPDATE, DELETE"
SEQ_PRIVS = "USAGE, SELECT"


def runtime_role(bind: sa.engine.Connection) -> str | None:
    """需要授权的运行时角色；未分离或角色不存在时返回 None（并记日志）。"""
    role = make_url(str(settings.DATABASE_URL)).username
    me = bind.execute(sa.text("SELECT current_user")).scalar()
    if not role or role == me:
        log.info("D83 runtime role %r == migration role: skip grants", role)
        return None
    if not bind.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
    ).first():
        log.warning(
            "D83 runtime role %r does not exist: grants skipped "
            "(create the role, then re-apply this migration)",
            role,
        )
        return None
    return role


def grant_statements(role: str, db: str) -> list[str]:
    r = '"' + role.replace('"', '""') + '"'
    d = '"' + db.replace('"', '""') + '"'
    return [
        f"GRANT CONNECT ON DATABASE {d} TO {r}",
        f"GRANT USAGE ON SCHEMA public TO {r}",
        f"GRANT {TABLE_PRIVS} ON ALL TABLES IN SCHEMA public TO {r}",
        f"GRANT {SEQ_PRIVS} ON ALL SEQUENCES IN SCHEMA public TO {r}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT {TABLE_PRIVS} ON TABLES TO {r}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT {SEQ_PRIVS} ON SEQUENCES TO {r}",
        f"REVOKE ALL ON alembic_version FROM {r}",
        f"GRANT SELECT ON alembic_version TO {r}",
    ]


def upgrade():
    bind = op.get_bind()
    role = runtime_role(bind)
    if not role:
        return
    db = bind.execute(sa.text("SELECT current_database()")).scalar()
    for stmt in grant_statements(role, str(db)):
        op.execute(stmt)
    log.info("D83 runtime role %r granted on %s", role, db)


def downgrade():
    bind = op.get_bind()
    role = runtime_role(bind)
    if not role:
        return
    r = '"' + role.replace('"', '""') + '"'
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE {TABLE_PRIVS} ON TABLES FROM {r}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE {SEQ_PRIVS} ON SEQUENCES FROM {r}"
    )
