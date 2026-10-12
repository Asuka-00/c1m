# 开发指南

## 目录结构（模块化单体）

```
backend/
  app/
    main.py          FastAPI 应用：按模块注册表挂载路由
    modules.py       组合根：模块的有序清单（决定规格加载、路由挂载顺序）
    models.py        聚合导入全部表（Alembic / 关系配置用）
    bootstrap.py     初始化：RBAC、首个超级用户、菜单、配置、默认租户
    core/            配置、数据库、安全、RLS、租户上下文、分页、依赖、迁移助手、模块注册表
      spec/          规格引擎：engine（实体→表）、query / write / validate / serialize / audit / excel
    platform/        平台模块：auth、users、rbac、tenants、menus、config、files、audit
    mes/             MES 领域模块：common、factory、product、equipment、process、
                     quality、lot、planning、execution
      demo.py        演示数据编排（按依赖顺序组合各模块的 demo.py）
    testing/         共享测试工具（用户、令牌、MES 测试客户端）
    tests/           架构（导入规则）测试
    alembic/         数据库迁移
  conftest.py        共享 pytest fixtures（独立测试库 app_test）
  scripts/           prestart、DB 角色、演示数据、i18n 导出、测试、lint
frontend/
  src/
    features/
      platform/      auth、users、rbac、tenants、menus、config、settings
      mes/           common（通用实体页/表单/表格）、product、process、lot、planning、execution
                     registry.tsx 组合各模块的实体扩展；pages.ts 组合各模块页面
      shell/         dashboard、errors、dynamic（菜单 component → 页面 的动态注册表）
    components/      通用组件（shadcn/ui、布局、CRUD、描述列表）
    lib/api/         client / request / types / hooks；platform/*、mes/{common,process,planning,execution}
    i18n/locales/    zh-CN / ja / en 文案（mes/ 为规格导出）
```

### 后端模块约定

每个模块是 `app/platform/<x>` 或 `app/mes/<x>` 下的包，按需包含：

| 文件 | 作用 |
| --- | --- |
| `module.py` | 调用 `app.core.registry.register(Module(...))` 声明：名称、路由（`"pkg.mod:router"` 字符串，延迟导入）、权限模块与额外权限、菜单项 / 菜单提供函数、规格与校验器模块 |
| `models.py` / `schemas.py` | SQLModel 表 / API 模型（平台模块） |
| `specs.py` | 声明式实体规格（MES 模块，替代 models） |
| `service.py` | **模块对外的唯一 API**（其余文件为内部实现） |
| `router.py` | FastAPI 路由（适配层） |
| `permissions.py` / `menus.py` | 权限编码、页面菜单 |
| `validators.py` | 通用 CRUD 的实体校验器（`@validator("entity")`） |
| `demo.py` | 该模块的演示数据（`add(...)`） |
| `tests/` | 该模块的测试 |

新增模块：建包 → 写 `module.py` → 在 `app/modules.py` 中按依赖顺序导入。路由按 `router_priority`（默认 100）稳定排序挂载，通配路由（如 `/mes/{entity}`，priority 200）排在具体路由之后。

### 分层与导入规则

```
core  <-  platform.*  <-  mes.common  <-  mes.<domain>  <-  mes.execution
```

- `app.core` 不导入 `platform` / `mes`；`platform` 不导入 `mes`（需要 MES 信息时经注册表获取，如权限、菜单）。
- MES 领域依赖（只能向左）：`factory`、`product` → common；`equipment` → common、product；`process` → + equipment；`quality` → + process；`lot` → + quality；`planning` → + lot；`execution` 可依赖所有领域，任何模块都不得依赖 `execution`。
- 跨模块只能导入对方的公开面：`service`、`models`、`schemas`、`specs`、`permissions`、`menus`、`deps`（`core` 与 `mes.common` 为共享内核，全部公开）。
- 模块间无循环依赖（`router*.py` / `deps.py` / `module.py` 为组合边界，不计入循环检查；`if TYPE_CHECKING:` 中的导入忽略）。需要“反向”通知时使用钩子，例如 `users.service.USER_CREATED_HOOKS`（tenants 注册个人工作区创建）。
- 规则由 `app/tests/test_architecture.py`（随 pytest 运行）强制执行。

> 注意：包名 `app.platform` 与标准库 `platform` 同名，不要以 `python app/xxx.py` 方式运行脚本（会把 `app/` 放进 `sys.path`），请使用 `python -m app.xxx`。

## 多租户与 RLS

- 所有业务表带 `tenant_id`，迁移中通过 `enable_rls()` 启用 Postgres 行级安全策略。
- 租户解析顺序：请求头 `X-Tenant-ID` > JWT `tid` 声明 > 用户唯一租户；后端在事务中设置 `app.current_tenant` 会话变量，RLS 策略（`app/core/rls.py`，会话变量由 `app/core/tenant.py` 设置）据此过滤。
- 运行时连接角色 `app_user` 不是表 owner 且 `NOBYPASSRLS`，因此即使代码遗漏过滤条件也无法跨租户读写。迁移使用 `MIGRATION_DATABASE_URL`（owner）。

## RBAC

- 权限编码为 `<资源>:<动作>`，如 `mes.lot:write`、`mes.exec:override`。实体权限由规格自动生成，读写权限按各模块 `permissions.py` 的 `PERM_MODULES` 自动生成，额外权限在 `PERMISSIONS` 中声明（经 `module.py` 注册），新增权限需在迁移中 `add_permissions()`。
- 角色按租户分配；超级用户拥有全部权限。前端通过 `/mes/_meta` 等接口获取当前权限控制按钮显示，后端在每个路由中再校验。

## 动态菜单

- 菜单项由各模块提供（平台页面见 `app/platform/menus/service.py`，MES 实体菜单由 `app/mes/common/menus.py` 按规格生成，执行/投产页面见各模块 `menus.py`），分组与标题在 `app/platform/menus/layout.py`；`GET /menus/me` 按用户权限返回可见树。
- 前端侧边栏完全由该接口渲染；新增页面需在后端模块 `menus.py` 声明菜单项，并在前端对应模块的 `pages.ts` 注册 component 键，图标名称在 `components/layout/icons.ts` 注册。

## MES 规格系统

- 每个实体用声明式规格描述（各 MES 模块的 `specs.py`）：字段、类型、引用、枚举、校验、三语标签。
- `app/core/spec/engine.py` 的 `build_table` 根据规格生成 SQLAlchemy 表（`registry.load()` 按模块顺序加载规格后统一构建）；通用路由 `app/mes/common/router.py` 提供列表 / 详情 / 新增 / 修改 / 删除 / 导入导出。
- 前端 `features/mes/common` 读取同一份元数据自动生成表格列、表单与筛选，因此大多数主数据页面无需手写；实体专属面板/按钮在各模块 `extensions.ts(x)` 中声明。
- 修改规格后需新增 Alembic 迁移（`alembic revision -m "..."` 并手写变更）。
- 业务逻辑：`mes/execution`（`stages.py` / `track_out.py` 四阶段作业、`checks/` 卡控注册表与检查类型、`consumption.py` 物料消耗、`hold.py` 暂停/释放、`split.py` / `merge.py` 分批合批）、`mes/planning/service.py`（工单与投产）、`mes/lot`（批次历史、单元、Q-Time）、`mes/process`（路线导航）、`mes/equipment`（E10 自动迁移）、`mes/quality`（DC 与抽样）。

## i18n

- 前端文案在 `frontend/src/i18n/locales/{zh-CN,ja,en}.json`，三语键必须一致。
- 规格中的标签可用 `backend/scripts/export_mes_i18n.py` 导出到前端文案。
- `pnpm i18n:check` 校验缺失 / 多余键（构建时自动执行）。

## 检查命令

后端（`backend/`）：

```bash
uv run ruff check app scripts conftest.py && uv run ruff format --check app scripts conftest.py
uv run mypy app && uv run ty check app
uv run alembic check            # 模型与迁移一致
bash scripts/test.sh            # pytest（含导入规则测试）+ coverage，使用 app_test 数据库
```

前端（`frontend/`）：

```bash
pnpm exec tsc -b
pnpm lint
pnpm format:check
pnpm i18n:check
pnpm build
```

UI 布局巡检（需前后端已启动）：`node scripts/ui-audit.cjs`。
