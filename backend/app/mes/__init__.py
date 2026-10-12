"""Semiconductor MES master-data modeling (no transactions).

Entities are declared once in ``app.mes.specs`` (fields, labels in en/zh/ja,
enums, refs, tree/version flags); ``app.mes.core`` turns every spec into a
tenant-scoped SQLAlchemy table (RLS via ``app.rls``) and ``app.mes.service`` +
``app.api.routes.mes`` provide the generic CRUD / tree / version / import-export
API. The frontend renders every entity from ``GET /mes/meta``.
"""
