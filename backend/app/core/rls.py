"""通用 Postgres 行级安全（RLS）工具，用于租户表。

租户隔离分两层：

1. 应用层：路由显式按租户过滤（``tenant_scoped``）。
2. 数据库兜底：RLS。每个请求设置事务级参数 ``app.current_tenant``（``set_tenant`` +
   Session ``after_begin`` 钩子，即 ``SET LOCAL``），租户表的策略只暴露 / 接受
   ``tenant_id`` 与之相等的行；未设置租户时看不到任何行。

运行时以非 owner、无 BYPASSRLS 的角色（如 ``app_user``，由 DBA 预先创建；表权限由迁移
0036 授予，D83 起不再运行 ``scripts/setup_db_roles.py``）连接；迁移以 owner 运行。``FORCE ROW LEVEL SECURITY`` 使策略对 owner 同样生效。

新增租户表时：模型加 ``tenant_id`` 外键列（ondelete CASCADE、索引）；迁移在建表后执行
:func:`enable_tenant_rls_sql` 返回的语句（降级用 :func:`disable_tenant_rls_sql`）；路由中用
``tenant_scoped`` 查询，插入前调用 ``set_tenant``（策略的 WITH CHECK 需要）。
"""

RLS_POLICY = "tenant_isolation"
RLS_EXPR = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def enable_tenant_rls_sql(table: str, policy: str = RLS_POLICY) -> list[str]:
    """生成为租户表启用 RLS 的 SQL 语句。

    Args:
        table: 表名。
        policy: 策略名。

    Returns:
        依次执行的 SQL 语句列表（ENABLE/FORCE RLS + 按 ``app.current_tenant`` 过滤的策略）。
    """
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {policy} ON {table} USING ({RLS_EXPR}) WITH CHECK ({RLS_EXPR})",
    ]


def disable_tenant_rls_sql(table: str, policy: str = RLS_POLICY) -> list[str]:
    """生成删除租户 RLS 策略并关闭 RLS 的 SQL 语句。"""
    return [
        f"DROP POLICY IF EXISTS {policy} ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]
