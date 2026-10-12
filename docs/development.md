# 开发指南

## 目录结构

```
backend/
  app/
    api/routes/     REST 路由（登录、用户、租户、RBAC、菜单、通用 MES CRUD、执行、工单）
    core/           配置、数据库、安全、租户上下文
    mes/            MES 领域：实体规格（specs_*.py）、执行、卡控、分批合批、演示数据
    alembic/        数据库迁移
  scripts/          prestart、DB 角色、演示数据、测试、lint
  tests/
frontend/
  src/
    features/       页面与业务组件（mes/、users/、permissions/ …）
    components/     通用组件（shadcn/ui、布局、CRUD、描述列表）
    lib/api/        API 客户端与类型
    i18n/locales/   zh-CN / ja / en 文案
```

## 多租户与 RLS

- 所有业务表带 `tenant_id`，迁移中通过 `enable_rls()` 启用 Postgres 行级安全策略。
- 租户解析顺序：请求头 `X-Tenant-ID` > JWT `tid` 声明 > 用户唯一租户；后端在事务中设置 `app.current_tenant` 会话变量，RLS 策略（`app/rls.py`）据此过滤。
- 运行时连接角色 `app_user` 不是表 owner 且 `NOBYPASSRLS`，因此即使代码遗漏过滤条件也无法跨租户读写。迁移使用 `MIGRATION_DATABASE_URL`（owner）。

## RBAC

- 权限编码为 `<资源>:<动作>`，如 `mes.lot:write`、`mes.exec:override`。实体权限由规格自动生成，额外权限在 `app/mes/core.py` 的 `EXTRA_PERMISSIONS` 中声明，新增权限需在迁移中 `add_permissions()`。
- 角色按租户分配；超级用户拥有全部权限。前端通过 `/mes/_meta` 等接口获取当前权限控制按钮显示，后端在每个路由中再校验。

## 动态菜单

- 菜单由后端定义（`app/mes/menus.py` 等），`GET /menus/me` 按用户权限返回可见树。
- 前端侧边栏完全由该接口渲染；新增页面需同时注册前端路由与后端菜单项，图标名称在 `components/layout/icons.ts` 注册。

## MES 规格系统

- 每个实体用声明式规格描述（`app/mes/specs_*.py`）：字段、类型、引用、枚举、校验、三语标签。
- `core.build_table` 根据规格生成 SQLAlchemy 表；通用路由 `app/api/routes/mes.py` 提供列表 / 详情 / 新增 / 修改 / 删除 / 导入导出。
- 前端 `useMesEntity()` 读取同一份元数据自动生成表格列、表单与筛选，因此大多数主数据页面无需手写。
- 修改规格后需新增 Alembic 迁移（`alembic revision -m "..."` 并手写变更）。
- 业务逻辑：`execution.py`（四阶段作业）、`checks.py`（卡控规则）、`splitmerge.py`（分批合批）、`wo.py`（工单与投产）。

## i18n

- 前端文案在 `frontend/src/i18n/locales/{zh-CN,ja,en}.json`，三语键必须一致。
- 规格中的标签可用 `backend/scripts/export_mes_i18n.py` 导出到前端文案。
- `pnpm i18n:check` 校验缺失 / 多余键（构建时自动执行）。

## 检查命令

后端（`backend/`）：

```bash
uv run ruff check app tests && uv run ruff format --check app tests
uv run mypy app
bash scripts/test.sh            # pytest + coverage，使用 app_test 数据库
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
