"""Semiconductor MES feature modules.

Each sub-package is one domain module (common, factory, product, equipment,
process, quality, lot, planning, execution). Entities are declared in each
module's ``specs.py`` (fields, labels in en/zh/ja, enums, refs, tree/version
flags); ``app.core.spec`` turns every spec into a tenant-scoped table (RLS via
``app.core.rls``) and provides the generic CRUD service; ``mes.common.router``
exposes the generic CRUD / tree / version / import-export API. The frontend
renders every entity from ``GET /mes/_meta``.
"""
