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

## 注释规范

注释用中文，标识符保持英文；只解释“为什么 / 业务规则”，不复述代码。

**后端（Python）**：PEP 257 + Google 风格文档字符串，由 `ruff` 的 pydocstyle（`D` 规则，
`convention = "google"`）强制检查。

- 每个模块文件开头写模块文档字符串：职责 / 包含内容。
- 公开类写类文档字符串，关键字段放在 `Attributes:`；公开函数 / 方法写摘要行，
  非平凡的服务函数补充 `Args:` / `Returns:` / `Raises:`（列出 HTTP 状态码）。
- 行内 `# 中文` 注释只用于不直观的业务规则：RLS 与租户解析、检查绑定优先级、Q-Time 时钟、
  拆合批继承、E10 迁移、扣料 FEFO、版本锁定等。
- 例外（`pyproject.toml` 中 per-file-ignores）：Pydantic / SQLModel 模型（`models.py`、
  `schemas.py`）与路由函数（`router*.py`）的文档字符串会进入 OpenAPI，为保持 API 契约不变不强制
  D101 / D103，模型用 `#` 注释说明；摘要以「。」结尾，故忽略 D415；`tests/`、`app/testing/`、
  `alembic/`、`scripts/` 不检查。

```python
def resolve(ctx: Ctx) -> list[tuple[Row, Row]]:
    """解析当前上下文生效的 (检查方案, 检查规则) 列表。

    仅保留最具体作用域的绑定（工步 > 设备 > 工序 > 设备类型 > 产品）。
    """
```

**前端（TS / React）**：TSDoc / JSDoc（`/** ... */`），中文。

- 导出的组件、Hook、工具函数、API 客户端与类型写 `/** ... */`；参数含义不直观时用
  `@param` / `@returns`。
- 功能模块文件（`src/features/**`）开头写一行文件头注释说明用途。
- 行内 `//` 注释只用于不直观的逻辑；`components/ui/`（shadcn 生成代码）保持原样。
- JSDoc 放在 `// eslint-disable-next-line` 之上，避免破坏 disable 指令。

## 检查命令

后端（`backend/`）：

```bash
uv run ruff check app scripts conftest.py && uv run ruff format --check app scripts conftest.py   # 含 pydocstyle（D）
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
pnpm test                        # vitest 组件 / 单元测试（无头 Chromium；首次需 pnpm exec playwright install chromium-headless-shell）
pnpm build
```

UI 布局巡检（需前后端已启动）：`node scripts/ui-audit.cjs`。

## RBAC：统一权限树

- 菜单与权限合并为一棵权限树：`Menu`（目录 / 页面）是 MENU 节点；`Permission.menu_id` 把权限挂到菜单下，`type` 为 MENU（页面访问）/ BUTTON（页面内操作）/ API。未挂接的权限归入“其他权限”分组。启动时 `seed_menus` → `link_permissions` 只为 `menu_id` 为空的权限补挂接，不覆盖手工调整。
- 角色与权限都有 `status`（active / disabled）；停用的角色或权限不授予任何权限（`rbac.service.active_codes`）。角色 `name` 为编码，`title` 为显示名称。
- 接口：
  - `GET /platform/permission-tree?space=all|workspace|platform&scope=platform|tenant`：权限树（超级用户）。
  - `GET /tenants/{id}/permission-tree`：租户角色对话框用的权限树（仅工作区、租户作用域）。
  - `PUT /platform/users/{id}/roles` `{role_ids}`：整体设置用户的平台角色。
  - 用户列表筛选 `username` / `full_name` / `is_active`；角色列表筛选 `code` / `title` / `status`；成员列表筛选 `username` / `full_name` / `is_active` / `role_id`。
- 前端：平台控制台“权限树”页（`platform-permissions`）维护菜单与权限；角色对话框内嵌三态复选权限树；不再有独立的菜单管理页与“角色权限”页签。
- 已删除的旧兼容管理接口（全部改用 `/platform/...`，仅超级用户）：`GET/POST /tenants/`、`GET /tenants/{id}/permissions`、`/users/` 列表 / 新建 与 `/users/{id}` 查询 / 修改 / 删除、`/roles/*`、`/permissions/*`、`/users/{id}/roles*`、`/menus/` 增删改查。保留的自助接口：`/users/me*`、`/users/signup`、`/menus/me`、`/tenants/me`、`/tenants/{id}/...`（工作区）。

### 平台权限与租户模拟

- 平台接口（`/platform/...`）按平台权限授权（`auth.deps.platform_permission`）：路径首段映射资源，GET 需 `<资源>:read`，其余需 `<资源>:write`；`users` 删除需 `users:delete`，设置用户角色需 `roles:write`，租户品牌属 `platform.config:*`。资源：`users`、`roles`（角色 / 权限 / 权限树 / 菜单）、`tenants`、`platform.config`、`platform.notify`、`platform.audit`。超级用户直接通过；非超级用户不能创建 / 修改 / 删除超级用户。
- 平台菜单带访问权限（`menus.service.PLATFORM_MENU_PERMS`），`/menus/me?space=platform` 按权限过滤；持有任一平台权限即可进入控制台（`/menus/me` 返回 `platform_access`）。
- 菜单 `status`（active / disabled）：停用的菜单对所有人隐藏，其路径进入 `forbidden_paths`（前端 403）。
- 内置权限 / 角色名称：`rbac.labels` 提供三语名称，种子数据补齐英文 `name` / `title`，`scripts/export_mes_i18n.py` 生成前端 `permName.*` / `roleName.*`；前端在名称为空或仍为内置英文名时按语言翻译（`lib/rbac-labels.ts`）。
- 以租户身份进入：`POST /platform/tenants/{id}/enter`（`tenants:write`）签发 `imp` 模拟令牌（`IMPERSONATION_EXPIRE_MINUTES`，默认 30 分钟），只能访问绑定租户（具全部租户权限）且不能调用平台接口；前端保存原令牌，退出（或模拟令牌过期）时恢复并调用 `POST /platform/tenants/{id}/exit`。进入 / 退出均记入平台操作日志。
