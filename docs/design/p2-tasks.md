# P2 任务卡（D51，依据 gap-list.md v0.3、bom.md、decisions.md D29–D50）

版本：v0.1（2026-10-14 架构师草案）。卡出来后各自在群里认领，认领后由架构师登记。

## 0. 通用约定（每张卡默认遵守，卡里不再重复）
- 分支：后端 `be/p2`、前端 `fe/p2`、设备集成 `eap/p2`、测试 `qa/p2`，都从 P1 当前本地提交拉出，不推送、不部署（D51）。P1 缺陷和复测优先。
- 权限码统一 `mes.<模块>:<动作>`；新接口先查认证和权限（401/403，不带字段明细），再校验请求体（D34）。
- P2 新接口按 §12 严格校验：未知字段、只读字段一律 422；报错路径用 Pydantic 数组写法，序号从 0 开始（D38）。动作接口（无请求体的）沿用 D32：空或 {} 放行，带字段 422。
- 时间：库里 timestamptz，接口输出 UTC 带 Z（§12、D45），新接口声明 response_model / UtcDateTime。
- 十进制：新接口的 Decimal 字段按定点字符串返回、去末尾零（D50）；输入接受字符串和数字，录入值超精度返回 422 too_many_decimals，不静默舍入（D49）。
- EAP 预留：凡是以后可能由设备上报的记录，表上带 `source`（manual/eap/…）和可空 `external_event_id`，唯一约束 (tenant_id, source, external_event_id)；手工接口传 source 返回 422，source 固定 manual（D30）。EAP 写入入口本期不做。
- 所有表带 tenant_id；编码类字段按租户唯一。新状态变化如需发领域事件，按 domain-events.md 命名 `<聚合>.<过去式>`，先在该文档登记再实现。
- 模块归属遵守 module-boundaries.md 的依赖方向，不新增反向依赖；新模块（如 shipping）单独建目录。

## 1. 后端（可立即开工）

### P2-B1 来料接收与 IQC
- 范围 做：客户来料/自有物料到货登记（来料单 + 明细）；IQC 检验单（抽样数、不良数、判定）；判定结果联动物料批状态（待检→合格/不合格/让步接收）；不合格可挂 Hold 或退回。不做：AQL 抽样表自动计算（只记录抽样数）、供应商评分、与 ERP 对接。
- 数据模型：`mes_receipt`（receipt_no 租户唯一、customer_id、ownership own/customer、received_at、status draft/received/closed）；`mes_receipt_line`（material_id、material_lot_no、customer_lot_no、qty Decimal(18,6)、uom、iqc_status pending/passed/rejected/waived）；`mes_iqc_inspection`（receipt_line_id、sample_qty、defect_qty、result pass/fail/waive、inspector、inspected_at、remark、source、external_event_id）。一条明细同一时间只能有一个未关闭的检验单。
- 接口：`/mes/receipt` 增查改、`POST /mes/receipt/{id}/receive`、`POST /mes/iqc`、`POST /mes/iqc/{id}/judge`。权限 `mes.receipt:read/write`、`mes.iqc:read/judge`。
- 依赖：P1 B7（mes_customer、ownership、customer_lot_no）。
- 验收：未检或不合格的物料批不能上料、不能投料（返回 409 iqc_not_passed）；让步接收必须填原因；客户批号按 D37 存原样、按大写比对；履历能从批次反查到来料单和 IQC 结果。
- 估工时：4 人日。建议认领：后端。

### P2-B2 包装层级与出货标签数据模型
- 范围 做：卷带/托盘→内盒→外箱→栈板的包装层级；装箱、拆箱；标签记录（标签号、模板、打印次数）；出货单与箱的关联。不做：标签模板设计器、打印机驱动（只生成打印数据 JSON）、客户 EDI。
- 数据模型：`mes_pack_unit`（pack_no 租户唯一、level reel/tray/inner_box/carton/pallet、parent_id、product_id、qty、customer_id、customer_lot_no、date_code、msl_level、status open/sealed/shipped/void）；`mes_pack_content`（pack_unit_id、lot_id、unit_id 可空、qty）；`mes_label`（pack_unit_id、label_no 唯一、template_code、payload JSON、print_count、last_printed_at）；`mes_shipment`（shipment_no、customer_id、status draft/confirmed/shipped）+ `mes_shipment_item`（pack_unit_id，一个箱只能在一个未作废的出货单里）。层级只能由小装进大，封箱后只读。
- 接口：`/mes/pack` 增查、`POST /mes/pack/{id}/pack`（装入下级或批次）、`/unpack`、`/seal`、`POST /mes/label/{pack_id}/print`（返回打印数据，记次数）、`/mes/shipment` 增查、`/confirm`、`/ship`。权限 `mes.pack:read/write`、`mes.label:print`、`mes.shipment:read/write/ship`。
- 依赖：P1 B7；P2-B3 的 MSL 字段（可后补）。
- 验收：装箱数量守恒（箱内合计 ≤ 批次可用数，超出 422）；同一箱不能混客户（422 customer_mismatch）；是否允许混客户批号由主数据开关控制（默认不允许）；封箱后改动返回 409；重印要记次数和原因。
- 估工时：5 人日（模型 2 + 接口与规则 3）。建议认领：后端。

### P2-B3 湿敏等级（MSL）与烘烤管控
- 范围 做：产品上配 MSL 等级和车间寿命（floor life）；批次/卷盘开封计时；超时须烘烤，烘烤记录重置计时；超时在进站卡控里拦截。不做：温湿度传感器采集（等 EAP）。
- 数据模型：产品加 `msl_level`、`floor_life_hours`；`mes_msl_exposure`（lot_id 或 pack_unit_id、opened_at、closed_at、accum_seconds、status open/sealed/expired）；`mes_bake_record`（对象、温度、时长、start/end、source、external_event_id）。
- 接口：`POST /mes/msl/{lot_id}/open`、`/seal`、`POST /mes/bake`；新增检查规则 `msl_floor_life`（off/warn/block，同 bom_required 三档）。权限 `mes.msl:write`。
- 依赖：无（包装字段与 B2 联动）。
- 验收：超时进站按规则 warn/block；烘烤后计时清零并写履历；计时累计跨多次开封正确。
- 估工时：3 人日。建议认领：后端（排在 B1、B2 之后）。

### P2-B4 客户级出货追溯
- 范围 做：按客户批号、出货单号、箱号/标签号正反向追溯到批次、晶圆、die 坐标（复用 P1 谱系）；导出。不做：新的谱系存储。
- 接口：`GET /mes/trace?kind=customer_lot|shipment|pack|label`。权限 `mes.trace:read`（沿用现有追溯权限，以后端现名为准）。
- 依赖：P2-B2、P1 B5/B7。
- 验收：从标签号查到晶圆 ID 和 die 坐标；从客户批号查到所有出货箱。
- 估工时：2 人日。建议认领：后端。

### P2-B5 坐标图列表接口
- 范围 做：`GET /mes/map` 分页列表，按基板编号、批次、导入时间、版本筛选，返回 substrate_map_id、map_version、导入人、来源。不做：版本选择拆批（见 P2-X1）。
- 依赖：P1 B4。权限 `mes.map:read`。page_size 上限 100。
- 验收：同一基板多版本都能列出、标出最新版本；时间带 Z。
- 估工时：1 人日。建议认领：后端。

### P2-B6 撤销单位转换（D41、D42）
- 范围 做：按 bom.md §10 规则撤销：所有子批都还是 WAITING 且没有后续交易才允许；母批恢复转换前状态，释放坐标图引用，删除或作废子批，写撤销事件。bin_split 同样适用。不做：部分撤销。
- 接口：`POST /mes/transform/{id}/revert`（动作接口，D32 请求体规则）；权限 `mes.exec:transform`。领域事件 `lot.transform_reverted`（先登记 domain-events.md）。
- 依赖：P1 B5、B8。
- 验收：有任何子批非 WAITING 或有后续交易返回 409 transform_not_revertible，details 列出原因批次；撤销后谱系里转换关系标为已撤销，追溯不再返回；Q-Time 起算点恢复。
- 估工时：2.5 人日。建议认领：后端。

### P2-B7 导出 xlsx 改为日期单元格（D46）
- 范围 做：所有 xlsx 导出的时间列改成 Excel 日期单元格，按租户时区换算，列名标时区（如「创建时间 (UTC+8)」）。接口 JSON 仍为 UTC Z。不做：CSV 导出。
- 依赖：无。
- 验收：各导出用 openpyxl 读回是 datetime 类型；时区标注正确；TZ=Asia/Taipei 与 UTC 部署结果一致。
- 估工时：1 人日。建议认领：后端。

### P2-B8 老接口未知字段日志（D44）
- 范围 做：Move In / Track In 等老接口收到未知字段时记一条结构化日志（接口、字段名、调用来源 source、客户端标识、用户、时间），不改行为；提供统计查询或日志汇总脚本。不做：本卡不收紧为 422（观察期后另开卡，由 kai mi 定时点）。可与 API-01/API-02 一起评估。
- 依赖：无。
- 验收：带未知字段请求仍返回原结果；日志能按字段和来源汇总；不记录请求体里的敏感值。
- 估工时：1 人日。建议认领：后端。

### P2-B9 报警码与报警履历（实现）
- 范围 做：按 P2-E1 评审后的模型实现主数据和履历接口、报警联动（可配置触发 Hold 或机台状态）。不做：EAP 上报入口。
- 依赖：P2-E1。权限 `mes.alarm:read/write`。
- 估工时：3 人日。建议认领：后端（E1 定稿后）。

### P2-B10 耗材与工装寿命（实现）
- 范围 做：按 P2-E2 模型在现有 tool_life（equipment/status.py、检查规则 tool_life）上扩展探针卡、劈刀、模具、刀片的寿命计数与到期提醒。
- 依赖：P2-E2。权限沿用 `mes.equipment:*`，新增动作以后端现名为准。
- 估工时：3 人日。建议认领：后端（E2 定稿后）。

## 2. 设备集成（设备对接暂停，只做不连真实设备的）

### P2-E1 报警码数据模型
- 范围 做：报警码主数据和报警履历的表结构草案（对照 SEMI E5 S5F1/ALID、ALCD 分类）；与 Qual、Hold、E10 状态的联动点。不做：通信实现。
- 数据模型要点：`mes_alarm_code`（equipment_type 或 equipment_id、alid、alcd 分类、text 三语、severity、action none/hold_equipment/hold_lot）；唯一 (tenant_id, equipment_type, alid)；`mes_alarm_log`（equipment_id、alid、set_at、cleared_at、lot_id 可空、source、external_event_id）。
- 验收：书面草案放 `eap/p2` 分支 docs 下，架构师和后端评审通过。
- 估工时：1.5 人日。建议认领：设备集成。**已认领：设备集成（2026-10-14）**

### P2-E2 耗材寿命数据模型
- 范围 做：探针卡、劈刀、模具、刀片的寿命单位（次数、touchdown、shot、长度）、计数来源、到期动作；与 Qual、PM 的联动点；对照现有 tool_life 说明怎么扩展。
- 数据模型要点：`mes_consumable`（code 唯一、type、life_unit、max_life、warn_ratio、status in_use/idle/expired/scrapped）、`mes_consumable_usage`（equipment_id、lot_id、count、source、external_event_id）、装卸记录可复用 equipment_material_mount 思路。
- 估工时：1.5 人日。建议认领：设备集成。**已认领：设备集成（2026-10-14）**

### P2-E3 本地设备模拟器设计
- 范围 做：设计文档：HSMS 被动/主动模式、S1/S2/S5/S6 最小消息集、事件和报警脚本化回放、产生 external_event_id 的规则，用于以后联调和自动化测试。本卡只写设计，不连真实设备；实现另开卡。
- 估工时：2 人日。建议认领：设备集成。**已认领：设备集成（2026-10-14）**

### P2-E4 评审
- 范围：评审 P2-B1、B2、B3 中带 source/external_event_id 的表，确认以后 EAP 上报（来料、烘烤、报警、耗材计数）能直接写入不改表结构。
- 估工时：1 人日。建议认领：设备集成。**已认领：设备集成（2026-10-14）**

## 3. 前端（可先用 mock 做，联调依赖对应后端卡）

| 卡 | 标题 | 依赖 | 验收要点 | 工时 | 认领 |
|---|---|---|---|---|---|
| P2-F1 | FE-02 收尾：侧栏截断（Future Hold、Warehouse Management）、403 页面加顶栏、ref-select 清除按钮测试和无障碍 | 无 | 中英日不截断不折行；403 有顶栏；用 getByRole 找 ×，清除后 × 消失 | 1 | 前端 |
| P2-F2 | FE-03：菜单 key 清单改由后端 export_mes_i18n 导出，前端测试直接读取；跳转回归测试处理下划线→连字符，纳入 `<Kpi to=...>` | 后端导出加菜单 key（约 0.5 人日，并入 P2-B8 或单独小提交） | 删掉手工 fixture 后测试仍全过 | 1.5 | 前端 |
| P2-F3 | AUTH-01：登录框提示改为「用户名」（三语） | 无 | 三语文案；不改登录逻辑 | 0.25 | 前端 |
| P2-F4 | 来料与 IQC 页面（来料单、检验判定） | P2-B1 | 不合格必须填原因；无权限按钮置灰 | 3 | 前端 |
| P2-F5 | 包装与出货页面（装箱、拆箱、封箱、标签打印预览、出货单） | P2-B2 | 层级树显示；封箱后只读；重印要填原因 | 4 | 前端 |
| P2-F6 | MSL 计时与烘烤登记 | P2-B3 | 剩余车间寿命倒计时；超时红色提示 | 2 | 前端 |
| P2-F7 | 追溯页加出货单、箱号、标签号类型 | P2-B4 | 能查到晶圆和 die 坐标 | 1 | 前端 |
| P2-F8 | 坐标图列表页 + 单位转换撤销入口 | P2-B5、P2-B6 | 撤销前二次确认，不可撤销时显示原因批次 | 1.5 | 前端 |
| P2-F9 | 报警码主数据、报警履历；耗材寿命页面 | P2-B9、P2-B10 | 三语；寿命到期黄/红提示 | 3 | 前端 |

## 4. 测试

### P2-Q1 P2 测试计划与验收用例
- 范围：`qa/plans/p2-test-plan.md`；覆盖每张 B/F 卡的验收要点、通用约定（422 严格校验、D34 先权限、UTC Z、D50 字符串、幂等去重）、出货链路端到端（来料→IQC→生产→装箱→出货→追溯回晶圆）。
- 估工时：2 人日（计划）+ 随卡验收约 6 人日。建议认领：测试评审。

## 5. 待定，不分配
- **P2-X1 按指定 map_version 拆批（D42）**：待工艺专家确认版本选择规则后再拆卡。目前预览返回实际使用的 substrate_map_id 和 map_version，已够操作员确认。

## 6. P2 其余项（C 组，下一批卡，暂不细化）
机台上料材料有效期与回温时间；测试程序版本；测试机+分选机工站与各 site 良率；各工站按颗良率与损失；条/卷带追溯视图；ES/Split 工程批；外部触发 Hold 接口、批次优先级、Hot Lot、交期；MRB 降级与审批；CP 测试对接；委外；ECN 对在制批；重测与样品抽取；开批预检；机台能力认证履历；载具事件补全；Interlock E10 统计；替代料优先级（D31）；die 级图 canvas 显示。第一批卡认领过半后再拆。

## 7. 依赖顺序
- 后端：B5、B7、B8（各 1 天的小卡先清）→ B1 → B2 → B3 → B4 → B6；E1/E2 定稿后插入 B9、B10。
- 设备集成：E1 → E2 → E4（随 B1–B3 草稿）→ E3。
- 前端：F1、F3 → F2 → F8（B5/B6 后联调）→ F4 → F5 → F6 → F7 → F9。P1 剩余 F4、F8、F7 先做完。
- 测试：Q1 先出计划，随卡验收；P1 复测始终优先。

## 8. 工时汇总（人日）
| 角色 | 卡 | 小计 |
|---|---|---|
| 后端 | B1 4、B2 5、B3 3、B4 2、B5 1、B6 2.5、B7 1、B8 1、B9 3、B10 3、F2 配套 0.5 | 26 |
| 设备集成 | E1 1.5、E2 1.5、E3 2、E4 1 | 6 |
| 前端 | F1 1、F2 1.5、F3 0.25、F4 3、F5 4、F6 2、F7 1、F8 1.5、F9 3 | 17.25 |
| 测试 | Q1 计划 2 + 随卡验收 6 | 8 |
| 合计（第一批） | | 57.25 |
第 6 节其余 C 组项未计入，粗估另需 35–45 人日。


### P2-E5 本地设备模拟器实现（模式 A）
- 工时：6 人日；认领：设备集成；依据：D53、eap/p2/equipment-simulator-design.md
- 验收：YAML 场景可以重放，`external_event_id` 是固定的，只连 127.0.0.1；先做报警 Hold 和寿命到期两个场景，交给测试评审验收。


### P2-B11 EAP 写入入口 `POST /mes/eap/events`
- 工时：3 人日；认领：后端；依据：D54-1
- 验收：只允许服务账号调用；同一个 (tenant, source, external_event_id) 重放只处理一次；三类事件（E10 状态变化、报警、工具计数）都能写入，`source` 记成 `eap` 或 `simulator`。
