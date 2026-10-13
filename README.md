# C1M · 半导体 MES

基于 **FastAPI** 后端与 **shadcn-admin**（React + Vite）前端构建的半导体制造执行系统（MES）。
支持多租户（Postgres RLS 隔离）、RBAC 权限、后端驱动的动态菜单，以及中文 / 日文 / 英文三语界面。

## 功能

- **工厂建模**：工厂 / 区域 / 产线、设备与 E10 状态模型、载具、治具、光罩
- **产品与物料**：产品、BOM、物料批（线边库存）、计量单位
- **工艺管理**：工艺路线（版本、分支、返工路线）、工序、配方、数据采集（DC）计划
- **生产计划**：工单、批次投产向导、编码规则
- **生产执行**：进站 / 上机 / 下机 / 出站四阶段作业、Q-Time、DC 录入、报废 / 返工、Hold / Release
- **批次管理**：分批 / 合批、批次谱系、批次履历
- **卡控**：可配置的检查规则库、规则组与触发点绑定，支持阻断 / 警告与授权放行
- **系统**：用户、角色、权限树、租户、审计日志、Excel 导入导出

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.14、FastAPI、SQLModel / SQLAlchemy、Alembic、Postgres（RLS）、uv |
| 前端 | React 19、Vite、TypeScript、TanStack Router / Query、shadcn/ui、Tailwind CSS、i18next、pnpm |

## 快速开始

### 1. 准备 Postgres

需要 Postgres 15+。应用使用两个角色：

- **owner 角色**（如 `postgres`）：执行迁移、建表，`MIGRATION_DATABASE_URL` 使用它；
- **app_user**：运行时连接角色，非 owner、`NOBYPASSRLS`，确保 RLS 生效，`DATABASE_URL` 使用它。`app_user` 由 `prestart` 自动创建 / 更新，无需手工建。

```bash
createdb -U postgres app
cp .env.example .env          # 修改 SECRET_KEY、两个数据库 URL 中的密码
cp frontend/.env.example frontend/.env
```

### 2. 后端

```bash
cd backend
uv sync
source .venv/bin/activate
bash scripts/prestart.sh      # alembic 迁移 + 创建 app_user + 初始数据（initial_data）
fastapi dev app/main.py       # http://localhost:8000 ，API 文档 /docs
```

演示数据（默认租户下的半导体样例：路线、设备、工单、批次、分批合批示例）：

```bash
uv run python scripts/mes_demo.py seed     # 写入
uv run python scripts/mes_demo.py remove   # 移除
```

### 3. 前端

```bash
cd frontend
pnpm install
pnpm dev                      # http://localhost:5173
```

默认登录：**admin / admin123**（来自 `.env` 中 `FIRST_SUPERUSER_USERNAME` / `FIRST_SUPERUSER_PASSWORD`，生产环境请务必修改）。

### 测试数据库

后端测试自动使用独立数据库 `app_test`（可通过 `TEST_DATABASE_NAME` 修改），不存在时自动创建并迁移：

```bash
cd backend && bash scripts/test.sh
```

## 项目结构

模块化单体：后端与前端按相同的领域划分。

```
backend/app/
  core/       配置、数据库、安全、RLS、分页、规格引擎（core/spec）、模块注册表
  platform/   auth · users · rbac · tenants · menus · config · files · audit
  mes/        common · factory · product · equipment · process · quality · lot · planning · execution
  modules.py  模块清单（组合根），main.py 据此自动挂载路由 / 权限 / 菜单 / 规格
frontend/src/
  features/platform/   auth · users · rbac · tenants · menus · config · settings
  features/mes/        common · product · process · lot · planning · execution
  features/shell/      dashboard · errors · 动态页面注册表
  lib/api/             按领域拆分的 API 客户端（platform/*、mes/*）
```

分层规则（`core ← platform ← mes.common ← mes.<领域> ← mes.execution`）由 `backend/app/tests/test_architecture.py` 强制执行，详见 [开发指南](docs/development.md)。

## 文档

- [开发指南](docs/development.md)：架构、多租户与 RLS、RBAC、动态菜单、MES 规格系统、i18n、检查命令

## 许可

MIT。本项目基于 [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template)（`LICENSE`）与 [shadcn-admin](https://github.com/satnaing/shadcn-admin)（`frontend/LICENSE`），保留其版权声明。
