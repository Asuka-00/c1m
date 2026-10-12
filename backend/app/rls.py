"""Generic Postgres row-level-security (RLS) helpers for tenant-scoped tables.

How tenant isolation works (two layers):

1. App layer — routes filter by tenant explicitly (``tenancy.tenant_scoped``).
2. DB backstop — RLS. Every request sets the per-transaction setting
   ``app.current_tenant`` (``tenancy.set_tenant`` + the Session ``after_begin`` hook,
   i.e. ``SET LOCAL``), and each tenant table carries a policy that only exposes /
   accepts rows whose ``tenant_id`` equals it. With no tenant set, nothing is visible.

The running app connects as a NON-owner role without BYPASSRLS (``app_user``, created
by ``scripts/setup_db_roles.py`` with DML default privileges); migrations run as the
owner. ``FORCE ROW LEVEL SECURITY`` additionally applies the policy to the owner.

Adding a new tenant-scoped table (e.g. ``invoice``):

* model: ``tenant_id: uuid.UUID = Field(foreign_key="tenant.id", nullable=False,
  ondelete="CASCADE", index=True)``
* migration, after ``op.create_table(...)``::

      from app.rls import enable_tenant_rls_sql, disable_tenant_rls_sql
      for stmt in enable_tenant_rls_sql("invoice"):
          op.execute(stmt)
      # downgrade: for stmt in disable_tenant_rls_sql("invoice"): op.execute(stmt)

* in routes use ``tenant_scoped(select(Invoice), Invoice, ctx.id)`` and call
  ``set_tenant(session, ctx.id)`` before inserts (the policy's WITH CHECK needs it).

``tests/api/routes/test_rls.py`` proves enforcement with a throw-away table built
by these same helpers.
"""

RLS_POLICY = "tenant_isolation"
RLS_EXPR = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def enable_tenant_rls_sql(table: str, policy: str = RLS_POLICY) -> list[str]:
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {policy} ON {table} USING ({RLS_EXPR}) WITH CHECK ({RLS_EXPR})",
    ]


def disable_tenant_rls_sql(table: str, policy: str = RLS_POLICY) -> list[str]:
    return [
        f"DROP POLICY IF EXISTS {policy} ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]
