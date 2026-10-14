"""D83：迁移内给运行时角色授权，库只靠 ``alembic upgrade head`` 即可被应用使用。

背景：表级 GRANT 与 ``ALTER DEFAULT PRIVILEGES``（``pg_default_acl``）都是**库级**的。
过去授权只由 ``scripts/setup_db_roles.py`` 做，全新库只跑迁移时运行时角色对任何表都没有
权限，登录查 ``user`` 表即 ``permission denied`` → 500。该脚本还会改共用角色的密码，D83
起不再运行它。

本迁移（幂等，可重复执行）：

- 运行时角色名取 ``settings.DATABASE_URL`` 的 username，不硬编码；与迁移角色相同
  （未分离）时跳过并记日志。
- 角色不存在：**跳过并记 WARNING**（不建角色、不改密码）。选跳过而非报错，是为了不让
  没有运行时角色的环境（如只用 owner 的单机部署）无法升级。**注意：之后不会自动补授权**
  （本迁移已记为完成，后续迁移不再执行它）。补救：DBA 建好角色后，用迁移角色执行
  ``python scripts/grant_runtime_role.py``（只执行本迁移同一组幂等 GRANT /
  默认权限语句，不建角色、不改密码；**不要**用 downgrade/upgrade 重放，会连带回退
  之后的迁移）。
- GRANT CONNECT ON DATABASE <当前库>、USAGE ON SCHEMA public、表 DML、序列 USAGE/SELECT；
  ALTER DEFAULT PRIVILEGES FOR ROLE <迁移角色> IN SCHEMA public（表 DML、序列 USAGE/SELECT；
  迁移角色取 migration_database_url 的用户名，D83 补充一，明确默认权限属主，不依赖
  current_user）；alembic_version 先 REVOKE ALL 再只给 SELECT。

downgrade：只撤销本迁移设置的 default privileges（``FOR ROLE <迁移角色>`` 的表 DML、
序列 USAGE/SELECT）。**注意**：pg_default_acl 按 (属主, schema, 对象类型) 只存一条，若旧的
``setup_db_roles.py`` 曾以同一属主设过同样的默认权限，会被一并撤掉（无法区分来源）；
已授予的表 / 序列 / 库 / schema 权限不受影响（撤掉会让运行中的应用立刻无法访问数据，
降到 0035 的库仍需要它们）。降级后新建的表需由 DBA 手工授权或再次 upgrade。

角色口径（QA P3-3）：``runtime_role()`` 取 ``settings.DATABASE_URL`` 的用户名（运行时连接），
``migration_role()`` 取 ``settings.migration_database_url`` 的用户名（迁移连接，取不到时
current_user）；两者都从配置的连接 URL 取，而“是否分离”的判断用 current_user（实际执行
迁移的角色），二者一致时跳过授权。

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
            "D83 runtime role %r does not exist: grants skipped and will NOT be "
            "re-applied by later migrations. After creating the role run "
            "`python scripts/grant_runtime_role.py` as the migration role "
            "(do not downgrade/upgrade to replay).",
            role,
        )
        return None
    return role


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def migration_role(bind: sa.engine.Connection) -> str:
    """默认权限的属主：migration_database_url 的用户名（取不到时用 current_user）。"""
    return make_url(settings.migration_database_url).username or str(
        bind.execute(sa.text("SELECT current_user")).scalar()
    )


def grant_statements(role: str, db: str, owner: str | None = None) -> list[str]:
    """授权语句；``owner`` 为迁移角色，默认权限写成 ``FOR ROLE <owner>``（D83 补充一）。"""
    r = '"' + role.replace('"', '""') + '"'
    d = '"' + db.replace('"', '""') + '"'
    dp = "ALTER DEFAULT PRIVILEGES" + (f" FOR ROLE {_q(owner)}" if owner else "")
    dp += " IN SCHEMA public"
    return [
        f"GRANT CONNECT ON DATABASE {d} TO {r}",
        f"GRANT USAGE ON SCHEMA public TO {r}",
        f"GRANT {TABLE_PRIVS} ON ALL TABLES IN SCHEMA public TO {r}",
        f"GRANT {SEQ_PRIVS} ON ALL SEQUENCES IN SCHEMA public TO {r}",
        f"{dp} GRANT {TABLE_PRIVS} ON TABLES TO {r}",
        f"{dp} GRANT {SEQ_PRIVS} ON SEQUENCES TO {r}",
        f"REVOKE ALL ON alembic_version FROM {r}",
        f"GRANT SELECT ON alembic_version TO {r}",
    ]


def upgrade():
    bind = op.get_bind()
    role = runtime_role(bind)
    if not role:
        return
    db = bind.execute(sa.text("SELECT current_database()")).scalar()
    for stmt in grant_statements(role, str(db), migration_role(bind)):
        op.execute(stmt)
    log.info("D83 runtime role %r granted on %s", role, db)


def downgrade():
    """撤销本迁移的默认权限（见模块说明：同属主同内容的旧默认权限会一并撤掉）。"""
    bind = op.get_bind()
    role = runtime_role(bind)
    if not role:
        return
    r = _q(role)
    dp = f"ALTER DEFAULT PRIVILEGES FOR ROLE {_q(migration_role(bind))} IN SCHEMA public"
    op.execute(f"{dp} REVOKE {TABLE_PRIVS} ON TABLES FROM {r}")
    op.execute(f"{dp} REVOKE {SEQ_PRIVS} ON SEQUENCES FROM {r}")
