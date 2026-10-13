"""用户名作为主身份：回填 / 规范化用户名（必填、小写、lower 唯一索引），邮箱可空；
审计 / 日志 / 更新人等操作人字段由邮箱转换为用户名。

Revision ID: 389542902fa8
Revises: d696a5de363d
Create Date: 2026-10-13 11:50:00

"""

import re

import sqlalchemy as sa
from alembic import op

revision = "389542902fa8"
down_revision = "d696a5de363d"
branch_labels = None
depends_on = None

_BAD = re.compile(r"[^a-z0-9_.-]")


def _derive(email: str | None, uid: str) -> str:
    """由邮箱本地部分推导合法用户名（3–50 位 a-z0-9_.-）。"""
    base = _BAD.sub("", (email or "").split("@")[0].lower())[:40]
    if len(base) < 3:
        base = f"user-{uid[:8]}"
    return base


def _rls_update(conn: sa.Connection, table: str, sql: str) -> None:
    """对启用 FORCE RLS 的表临时取消 FORCE 后执行更新（迁移以 owner 运行）。"""
    forced = conn.execute(
        sa.text("SELECT relforcerowsecurity FROM pg_class WHERE relname = :t"),
        {"t": table},
    ).scalar()
    if forced:
        conn.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
    conn.execute(sa.text(sql))
    if forced:
        conn.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text('SELECT id::text, username, email FROM "user" ORDER BY created_at NULLS LAST, id')
    ).all()
    taken: set[str] = set()
    final: dict[str, str] = {}
    # 先保留已有的合法用户名（转小写），再为缺失 / 冲突者生成
    for uid, uname, _ in rows:
        if uname and uname.lower() not in taken:
            final[uid] = uname.lower()
            taken.add(uname.lower())
    for uid, _, email in rows:
        if uid in final:
            continue
        base, n, cand = _derive(email, uid), 1, ""
        cand = base
        while cand in taken:
            n += 1
            cand = f"{base}-{n}"
        final[uid] = cand
        taken.add(cand)
    for uid, uname, _ in rows:
        if uname != final[uid]:
            conn.execute(
                sa.text('UPDATE "user" SET username = :u WHERE id = CAST(:i AS uuid)'),
                {"u": final[uid], "i": uid},
            )
    op.alter_column("user", "username", existing_type=sa.String(50), nullable=False)
    op.alter_column("user", "email", existing_type=sa.String(255), nullable=True)
    op.create_index(
        "uq_user_username_lower", "user", [sa.text("lower(username)")], unique=True
    )

    # 操作人字段：邮箱 -> 用户名（按邮箱不区分大小写匹配）
    m = "(SELECT u.username FROM \"user\" u WHERE lower(u.email) = lower({col}))"
    targets = [
        (r[0], r[1])
        for r in conn.execute(
            sa.text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND ("
                "column_name = 'user_email' OR (table_name = 'platform_audit' AND column_name = 'actor_email') "
                "OR (table_name = 'login_log' AND column_name = 'email') "
                "OR (table_name IN ('user', 'role') AND column_name = 'updated_by'))"
            )
        ).all()
    ]
    for table, col in targets:
        sub = m.format(col=f'"{table}".{col}')
        _rls_update(
            conn,
            table,
            f'UPDATE "{table}" SET {col} = {sub} WHERE {col} LIKE \'%@%\' AND {sub} IS NOT NULL',
        )


def downgrade() -> None:
    op.drop_index("uq_user_username_lower", table_name="user")
    op.alter_column("user", "email", existing_type=sa.String(255), nullable=False)
    op.alter_column("user", "username", existing_type=sa.String(50), nullable=True)
