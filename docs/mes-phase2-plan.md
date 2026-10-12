# MES 二期实施计划（生产执行深化）

> 范围：EDC、返工、在制报废/补数、Q-Time、设备（E10 手动/PM/停机）、配方管控、履历与追溯、Hold 管理、WIP 看板与报表。
> 暂缓：派工（Dispatching）、电子签名（e-Signature）。
> 约定沿用一期：模块化单体（core ← platform ← mes.common ← 业务域 ← execution）、`module.py` 注册、
> tenant_id + RLS、RBAC + 后端菜单、三语 i18n、中文 docstring / TSDoc、标准 CRUD 表格（服务端分页排序 20 行、搜索、下拉筛选）。

## 0. 总体原则：所有管控都可开关（复用卡控规则体系）

一期已有「卡控规则 → 卡控方案 → 卡控绑定（触发时机 × 作用域：工步 > 设备 > 工序 > 设备类型 > 产品，最具体者生效）」。
二期不新建开关表，而是扩展该体系：

- **严重度新增 `off`（关闭）**：卡控规则 severity = block | warn | **off**。
  在某作用域绑定一个含 `off` 规则的方案，即在该工步 / 设备 / 工序等处**关闭**该类管控（最具体作用域覆盖更宽泛作用域）。
- **内置管控默认开启**：执行逻辑内置的管控（超规处置、物料不足、Q-Time 超时处置、返工次数上限、数量调整上限、配方匹配……）
  在没有任何绑定时保持开启；只有解析到同类型的 `off` 规则时关闭。统一入口 `checks.enabled(ctx, check_type)`。
- 规则 / 方案 / 绑定的 `is_active` 仍然有效（停用 = 不参与解析）。
- 每次关闭生效时在卡控记录中写一条 `pass`（消息“disabled by rule X”），保证可审计。

## 1. 现状盘点（一期已具备）

| 能力 | 已有 | 缺口 |
|---|---|---|
| EDC | DC 计划 / 量测项目 / 抽样；Track Out 录入、规格判定、超规处置（block>rework>auto hold>warn）；dc_complete / oos 规则 | 超规处置不可按工步关闭；无 EDC 数据查询的超规高亮 / 统计 |
| 返工 | 工步返工流程、返工晶圆、rework_count（晶圆） | 无返工次数上限；无跳站（手动 jump） |
| 报废 / 补数 | Track Out 时按晶圆 / 数量报废 | 无在制（任意时点）报废；无补数（Bonus）；无数量调整上限 |
| Q-Time | 规则、时钟（谱系继承）、Move In 时超时处置 | 等待中超时不会自动 Hold；无 Q-Time 监控页 |
| 设备 | E10 状态模型、自动迁移 | 无手动改状态 + 历史；无 PM 计划；无停机记录 |
| 配方 | recipe_active / eqp_capability 规则 | 无「设备-配方」匹配关系与检查 |
| 履历追溯 | 批次履历页、谱系 | 无正 / 反向追溯（批次/晶圆/设备/物料） |
| Hold | Hold 记录、单批释放 | 无 Hold 管理页批量释放（按原因） |
| 报表 | 无 | WIP 看板、产出、良率、OEE |

## 2. 分期

### 阶段 1：EDC 执行完善
- 内置管控开关：`check_severity` 增加 `off`；`checks.enabled()`；`run()` 跳过 off 规则。
- Track Out 超规处置受 `oos` 开关控制（关闭时只记录 is_oos，不处置）；物料不足硬拦截受 `material_sufficient` 开关控制。
- EDC 数据查询（量测数据页）：超规值高亮、按批次 / 工步筛选（沿用 CRUD 表）。
- 测试：开关作用域覆盖（工步 off 覆盖产品 on）、关闭后不 Hold / 不返工。

### 阶段 2：返工
- 工步字段 `max_rework`（该工步返工次数上限，空 = 不限）；批次 `rework_count`（进入返工流程次数，按工步计于 `exec_ctx`/历史）。
- 新检查类型 `rework_limit`（内置，默认开）：超过上限时阻断进入返工（可放行），关闭则不限。
- 跳站（Jump）：`POST /mes/exec/lots/{id}/jump`，目标工步（同流程）、原因代码（reason_type=jump）、备注；
  仅等待状态、非 Hold；权限 `mes.exec:jump`；写历史 `jump`；可配卡控触发时机 `jump`。
- 批次作业页：跳站对话框。

### 阶段 3：在制报废 / 补数
- `POST /mes/exec/lots/{id}/adjust`：`{kind: scrap|bonus, qty | unit_ids, reason_id, comment}`。
  晶圆 / 单元级：选择单元报废；数量级：调整数量。补数仅数量级（晶圆级需新增单元，暂不支持）。
- 原因代码类型新增 `bonus`；权限 `mes.exec:adjust`；历史 `scrap` / `bonus`；工单 / 批次数量同步。
- 新检查类型 `qty_adjust_limit`（参数 `max_pct`，默认 10%）：单次调整超过比例阻断（可放行），可关闭。
- 触发时机新增 `adjust`，可绑定其他检查（如 lot_hold）。

### 阶段 4：Q-Time 计时与超时自动 Hold
- `sweep_qtime()`：扫描等待 / 进站中的批次，对已超时且动作为 hold 的规则自动 Hold（幂等）；
  `POST /mes/exec/qtime/sweep`（权限 mes.exec:hold）+ 后端定时任务（默认每 60 秒，配置项 `QTIME_SWEEP_SECONDS`，0 = 关闭）。
- 内置开关：检查类型 `qtime` 为 off 时，该工步的超时处置与扫描都跳过。
- Q-Time 监控页：在途批次的计时、剩余分钟、状态（正常 / 将超时 / 已超时）。

### 阶段 5：设备（E10 手动 / PM / 停机）+ 阶段 6：配方管控
- E10 手动改状态（按状态迁移表校验）+ 状态历史表（含自动迁移）；
- PM 计划（设备 / 设备类型、周期：天数或加工批次数、下次到期）、PM 执行记录；到期检查 `pm_due`（可关闭）。
- 停机记录（开始 / 结束 / 原因 / 关联 E10）。
- 设备-配方匹配表 `equipment_recipe`；Track In 检查 `recipe_match`（可关闭）。

### 阶段 7：履历与追溯 + 阶段 8：Hold 管理
- 追溯页：输入批次 / 晶圆 / 设备 / 物料批，正向（下游产出）与反向（上游来源、经过的设备、消耗的物料）。
- Hold 管理页：按原因 / 来源 / 产品筛选在 Hold 批次，批量释放（需释放原因代码），权限 mes.exec:hold。

### 阶段 9：WIP 看板与报表
- WIP：按工步 / 工序 / 状态的在制数量；产出：按日 / 工单；良率：报废与产出；OEE：基于 E10 时间（可用率 × 性能 × 良率）。

## 3. 交付与验收
每阶段：迁移（含 RLS / 权限）、菜单、三语、测试、全量检查（pytest / ruff / mypy / ty / alembic check / tsc / eslint / prettier / i18n / vitest / build）、
本地提交（不推送）、中文截图 `/workspace/screenshots/phase2/<n>-*`；演示数据改动后恢复开发库。

## 4. 待确认问题
1. 补数（Bonus）在晶圆级是否需要新增晶圆（含晶圆号生成）？当前方案仅数量级支持。
2. 返工次数上限按「工步」还是按「批次累计」？当前方案按工步，另记批次累计数供报表。
3. Q-Time 扫描是否需要「将超时预警」通知（当前仅在监控页标黄）？
4. OEE 的性能稼动率需要标准节拍（UPH），是否在设备 / 配方上维护？

## 5. 已确认决策（2026-10-12）

- 补数：晶圆级批次不允许补数（仅数量批次）。
- 返工上限：按工步计数（`route_step.max_rework`）。
- Q-Time：增加预警阈值 `qtime_rule.warn_minutes`（监控页“即将超时”）；内置后台定时扫描 `QTIME_SWEEP_SECONDS`（0 关闭，Postgres 咨询锁保证单实例执行）。
- OEE 理论产能：`recipe_equipment.ideal_uph` 优先，其次 `equipment.ideal_uph`；区间内缺少 UPH 时不计算性能稼动率与 OEE。
