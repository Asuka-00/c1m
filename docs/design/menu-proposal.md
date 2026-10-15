# 菜单调整方案（草案，待 kai mi 拍板）

> 作者：架构师 · 2026-10-13 23:0x
> 依据：`backend/app/platform/menus/layout.py`（现状），工艺专家评审 `process/reviews/fsft-fe-menu-review.md`，前端清单（群内），后端、测试评审、设备集成意见。
> 原则：本期只改菜单数据（`layout.py` 的分组、顺序、标题，以及少量权限种子），**路由不变，旧书签不 404**。新页面、新接口、新权限模型放下期。
> 说明：「返工/报废处置」里的报废指**批次报废**，与 D26 从 Q-Time 规则中去掉的 scrap 处置动作无关。

## 一、本期（方案 A：只改数据）

### A1 分组调整
| 序 | 分组 key | 新标题（en / zh / ja） | 说明 |
|---|---|---|---|
| 0 | g-workspace | Workspace / 工作台 / ワークスペース | 只留仪表盘；消息中心、个人设置移出侧栏（顶栏铃铛、头像菜单已有） |
| 10 | g-execution | Lot Operation / 批次作业 / ロット作業 | 只放操作员高频项 |
| 15 | g-exception（新） | Exception Handling / 异常处置 / 異常処置 | 本期只放已有页面：Future Hold、卡控记录 |
| 20 | g-wip | WIP & Inquiry / 在制与查询 / 仕掛・照会 | 报表 + 查询 |
| 30 | g-planning | 不变 | |
| 40 | g-warehouse | 不变 | |
| 50 | g-equipment | Tool Management / 机台管理 / 装置管理 | 以后 EAP 的通讯状态、报警页直接加在这一组 |
| 60–110 | 其余 | 不变 | |

### A2 新旧对照表（路由、权限都不变；权限列为现状）
| 菜单 key | 旧分组 → 新分组 | 旧中文 | 新中文 | 新英文 | 新日文 | 路由 | 权限 |
|---|---|---|---|---|---|---|---|
| mes-lot-console | 执行（1） | 批次作业 | 批次作业（进出站） | Lot Operation (Track In/Out) | ロット作業（着工・完了） | /mes/lot-console | mes.exec:read |
| mes-lot_hold | 执行（5 → 2） | Hold 管理 | 不变 | Hold Management | ホールド管理 | /mes/lot-hold | mes.exec:read |
| mes-qtime-monitor | 执行（4 → 3） | Q-Time 监控 | 不变 | Q-Time Monitor | Q-Time 監視 | /mes/qtime-monitor | mes.exec:read |
| mes-batch-ops | 执行 | 批量作业 | 不变 | 不变 | 不变 | /mes/batch-ops | mes.exec:read |
| mes-carrier-ops | 执行 | 载具管理 | 载具作业 | Carrier Operation | キャリア作業 | /mes/carrier-ops | mes.exec:read |
| mes-shift-handover | 执行 | 交接班日志 | 不变 | 不变 | 不变 | /mes/shift-handover | mes.exec:read |
| mes-label-print | 执行 | 标签打印 | 不变 | 不变 | 不变 | /mes/label-print | mes.exec:read |
| mes-future_hold | 执行 → 异常处置 | 预约 Hold | Future Hold（预约 Hold） | Future Hold | 予約ホールド | 现有实体路由 | 现有 |
| mes-check_log | 报表 → 异常处置 | 卡控记录 | 不变 | Interlock Log | インターロック記録 | 现有实体路由 | 现有 |
| mes-lot | 执行 → 在制与查询 | 批次列表 | 批次查询 | Lot Inquiry | ロット照会 | 现有实体路由 | 现有 |
| mes-wafer | 执行 → 在制与查询 | 晶圆 | 晶圆查询 | Wafer Inquiry | ウェーハ照会 | 现有实体路由 | 现有 |
| mes-yield-report | 在制 | 良率统计 | 良率报表 | Yield Report | 歩留まりレポート | /mes/yield-report | mes.exec:read |
| mes-dc_result | 质量 | 量测数据 | 不变 | Metrology / DC Data | 不变 | 现有 | 现有 |
| mes-operator_qual | 执行 → 工厂建模 | 操作员资质 | 不变 | 不变 | 不变 | 现有 | 现有 |
| mes-lot-start | 计划（移到组内第 1 项） | 投产 | 投片/开批【推断，需产线确认】 | Lot Start | ロット投入 | /mes/lot-start | mes.lot:start |
| mes-eqp-board | 机台管理 | 设备状态看板 | 机台状态看板 | Tool Status Board | 装置状態ボード | /mes/eqp-board | mes.equipment:read |
| mes-equipment-master | 机台管理 | 设备 | 机台主数据 | Equipment Master | 装置マスタ | /mes/equipment-master | 现有 |
| mes-tool | 机台管理 | 工具寿命 | 耗材/治具寿命 | Consumable Life | 消耗品・治具寿命 | 现有 | 现有 |
| mes-change_order | 工艺 | 工程变更 | 工程变更（ECN） | ECN | 設計変更（ECN） | 现有 | 现有 |
| mes-qtime_rule | 工艺 | Q-Time 规则 | 不变 | 不变 | Q-Time ルール | 现有 | 现有 |
| notifications / settings | 工作台 → 移出侧栏 | 消息中心 / 个人设置 | — | — | — | 路由保留 | 不变 |

合并菜单与首个页签重名的共 8 个（页签名不变）：仓库、设备、产品、物料、载具这 5 个改为「××主数据」（设备改为「机台主数据」）；E10 状态模型改为「E10 状态配置」，工艺流程改为「工艺流程配置」，工作日历改为「日历与班次」。

### A3 术语统一
- 日文 Q-Time 统一写成带空格的「Q-Time 監視」「Q-Time ルール」，前后端写法一致（后端改 `layout.py`，前端同步）。
- Hold：中文统一叫「Hold」（不叫冻结），日文统一叫「ホールド」，日文的 WIP 队列状态也改成「ホールド中」。
- 批次作业页里的「调度队列」改叫「在制队列」（WIP Queue / 仕掛キュー），免得被当成 RTD。
- 机台状态沿用 SEMI E10 的六种叫法，本期不改状态数据，只要求菜单和看板文字一致。

### A4 本期一并修的权限问题
- ~~给租户 admin 补上 `notify:config`~~（23:12 更正：admin 已经通过模块权限 `EXTRA_PERMISSIONS` 拿到了这项权限，不用改代码，只补一条测试：admin 有、member 没有）。
- **member 看到「用户与权限」属于权限给多了**：本期只把这个菜单的显示权限改为 `members:write`，member 不再显示。`members:read` 先保留，因为首页人数卡片在用（`dashboard/index.tsx:65`），收掉会报 403。
- **风险（已知缺口，23:57 更新）**：联调确认 member 的 `forbidden_paths` 已包含 `/user-permissions`，前端会直接拦住这个页面。剩下的缺口只有 `members:read` 接口还能直接调用，下期由 MENU-B4 关闭。

### 本期分工
- 后端：改 `layout.py` 和权限种子，做幂等同步；交付各角色测试账号脚本（含平台管理员）。
- 前端：改测试里写死的菜单文字，补齐三语文案，修改日文 Q-Time 写法。
- 测试评审：按 A2 表写菜单回归用例，覆盖各角色可见性、旧链接、三种语言。

## 二、下期

| 编号 | 内容 | 依赖 |
|---|---|---|
| MENU-B1 | 细化权限：作业、查询/报表、工程配置三类读权限；新增岗位角色（操作员、工程师、主管） | 后端迁移 |
| MENU-B2 | 对齐 6 项权限码与所在分组（Q-Time 规则、工具寿命、量测数据、原因代码、计量单位、配方执行记录） | 和 B1 一起做 |
| MENU-C1 | 全局菜单搜索（Ctrl/⌘K）、面包屑、Hold 和 Q-Time 超时的数量角标 | 只改前端 |
| MENU-C2 | 「常用」区（收藏 + 最近访问），先存在浏览器本地 | 只改前端 |
| MENU-C3 | 按角色设默认首页；批次作业页加最近批次和扫码直达 | 依赖 B1 |
| MENU-B4 | 新增精简的选人/人数接口，然后去掉 member 的 `members:read`，补上路由级权限守卫 | 后端 + 前端 |
| MENU-N1 | 返工/报废（批次报废）处置审批入口 | 需后端确认接口 |
| MENU-N2 | 设备 Qual 入口（后端已有 `execution/qual.py`，是否已有页面待确认） | 需后端确认 |
| MENU-N3 | 异常处置组里的「Hold 待处理（工程视图，按部门/原因）」 | 需后端确认；可与按部门限定 Hold 释放权限一起做 |

## 补充（23:15）
- 重名合并菜单的英文和日文标题：「XX 主数据」写 XX Master / XXマスタ；机台主数据写 Equipment Master / 装置マスタ；E10 状态配置写 E10 State Configuration / E10 状態設定；工艺流程配置写 Route Configuration / ルート設定；日历与班次写 Calendar & Shifts / カレンダー・シフト。
- 「在制队列」本期只改代码注释，不新增界面文案；界面显示记进下期（MENU-C4）。
