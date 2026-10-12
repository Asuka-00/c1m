"""半导体 MES 功能模块。

每个子包是一个业务域模块（common、factory、product、equipment、process、quality、lot、
planning、execution）。实体在各模块的 ``specs.py`` 中声明（字段、三语标签、枚举、引用、
树形/版本标记）；``app.core.spec`` 把规格转换为租户表（RLS 见 ``app.core.rls``）并提供通用
CRUD 服务；``mes.common.router`` 暴露通用 CRUD / 树 / 版本 / 导入导出接口；前端依据
``GET /mes/_meta`` 渲染所有实体页面。
"""
