# MES 第三阶段计划

13 项功能按顺序实施（P1 → P3），每项独立提交。通用约定：

- **管控开关**：所有新增管控均为检查类型（`check_type`），通过 检查规则 → 检查方案 → 检查绑定 配置；
  内置管控用 `enabled(ctx, 类型)` 判断，规则严重度为 `off` 时关闭，未配置时默认开启。
- **数据**：新增表走普通 Alembic 迁移（在 `0001_initial` 之后追加），租户表启用 RLS；无向后兼容代码。
- **界面**：标准 CRUD（每页 20 条、搜索、下拉筛选）、MES 标准术语、zh / ja / en 三语，
  页面说明为一句功能描述（受说明文案检查约束），工作区不出现“租户”字样。
- **其他**：中文 docstring / TSDoc，演示数据，pytest + vitest 全量检查。

## P1

| # | 功能 | 数据 | 接口 / 界面 | 管控（检查类型） |
|---|---|---|---|---|
| 1 | 晶圆级履历 + 晶圆图 | 复用 `lot_history.unit_id`；按谱系追溯晶圆所属批次 | `GET /mes/exec/wafers/{id}/history`、`GET /mes/exec/lots/{id}/wafer-map`；批次履历页增加晶圆图（槽位网格，按状态着色），点击晶圆查看履历 | — |
| 2 | 腔体 / 端口级管控 | `lot.chamber_ids`、`lot_history.details.chambers`；腔体为 `equipment.unit_kind=chamber` 的子设备，带 E10 状态 | Track In 选择腔体（多选，限当前设备的腔体）；腔体 E10 状态随 Track In / Out 迁移 | `chamber_available`（腔体 E10 可用）、`chamber_required`（工步要求选择腔体） |
| 3 | 配方版本 + 参数快照 | 配方 `version`；新表 `lot_recipe_run`（批次、工步、设备、配方及版本、参数快照 JSON） | Track In 时写入快照；批次履历可查看本次运行的配方参数 | `recipe_active`（已有）沿用 |
| 4 | 批量 Track In / Out | — | `POST /mes/exec/batch/{stage}`（同载具 / 同批次组的多批次，逐批执行同一参数，全部检查通过才提交） ；批次作业页多选批次执行 | `batch_same_step`（批量作业的批次须在同一工步、同一设备） |
| 5 | 载具管理 | 载具 `usage_count`、`max_usage`、`clean_interval_days`、`last_cleaned_at`、`carrier_status`；新表 `carrier_event`（换载具 / 合并 / 拆分 / 清洗） | 载具作业页：换载具、合并、拆分、登记清洗；载具事件列表 | `carrier_clean`（清洗到期）、`carrier_usage`（使用次数上限） |

## P2

| # | 功能 | 要点 |
|---|---|---|
| 6 | 良率统计 | 按工步 / 产品 / 批次统计投入、报废、良率；报废原因帕累托图 |
| 7 | 工单进度看板 | 工单完成进度、在制分布，交期临近 / 逾期预警 |
| 8 | 工程变更管理 | 流程 / 配方版本发布、生效日期；在制批次沿用旧版本或切换新版本（按变更单规则） |
| 9 | 预约 Hold（Future Hold） | 在指定工步预设 Hold，批次到达该工步 Move In 时自动 Hold；管控 `future_hold` |
| 10 | 批次优先级 / 急件 | 派工队列按优先级排序，急件（Hot Lot）高亮 |

## P3

| # | 功能 | 要点 |
|---|---|---|
| 11 | 交接班日志 | 按班次记录交接事项、未结事项，接班人确认 |
| 12 | 标签打印 | 批次 / 载具条码与二维码，可打印页面 |
| 13 | 操作员资质 | 工位 / 工序认证、有效期；到期前经通知提醒；Track In 检查 `operator_qualified` |

## 验收

每项：后端测试 + 前端测试、全量检查（ruff / mypy / alembic check / pytest / tsc / eslint / prettier / i18n 检查 / vitest）、
本地提交；全部完成后统一部署一次并验证健康状态；zh-CN 截图存于 `/workspace/screenshots/phase3/<序号>-*`。
