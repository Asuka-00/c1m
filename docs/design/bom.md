# BOM、机台上料与封测单位转换设计（v1.1，2026-10-14）

状态：正式版 v1.1（kai mi 2026-10-14 确认 v0.3 与分期，P1 开工；见 decisions.md D28）。kai mi 已定（2026-10-14）：前道、后道封测都要考虑。

## 1. 范围
- 首期：产品 BOM（版本化）、批次锁定版本、出站用量比对（只提示）、机台上料记录（手工录入）。
- P1 范围以第 8 节为准（含两级 BOM、替代料列表）。不做：审批流、版本差异对比、三级及以上 BOM、耗材寿命（见第 8 节分期）。

## 2. 数据模型
### bom（主表）
product_id（成品或半成品）, version, status(draft/active/superseded/void), effective_at,
confirmed_by, confirmed_at（生效时必填，代替审批流）
- 同一产品同时只有一个 active；新版本生效时旧版本自动 superseded，历史保留。
- active 后只读；提供“复制为新版本”。

### bom_line（明细）
bom_id, component_type(material/product), material_id 或 component_product_id,
qty + uom（用量单位：ea/g/m/strip/包装单位，带单位换算表 `uom_conversion`）,
per_basis（每多少“什么”：沿用 `track_unit_kind` wafer/strip/die/package/unit，另加 lot；默认 wafer）, scrap_rate, step_id(可空),
consume_mode(issue=出站扣料 / mounted=机台上料，不出站扣)
- 大宗气体、纯水、通用化学品不进 BOM。

### lot.bom_id
- 开批时锁定当时 active 版本；无 active 时允许开批、锁空并提示。
- 开关 `require_bom_on_lot_start`，默认关闭；现有产品与在制批次不迁移（bom_id 为空）。
- 拆批：子批沿用母批版本。合批：版本不同禁止，报错写明双方版本号。

### material_consumption（现有用料记录补字段）
source(step_resource/manual/eap)，usage_type(normal/rework/scrap)
- 返工与报废用量单独记，不参与损耗比对。

### equipment_material_mount（新表：机台上料记录）
equipment_id, position, material_id, material_lot, mounted_at, unmounted_at, source(manual/eap), operator
- 首期手工录入；以后 EAP 事件直接写入，不改表结构。
- 批次过站时可按时间区间反查当时机台装的材料批号（追溯用）。

## 3. 出站比对规则
- 只比 consume_mode=issue 的明细；基准 = 当前片数（basis=wafer）或 1（basis=lot）。
- 挂工步的明细在该工步出站比对；未挂工步的在最后一步出站统一比对。
- 实际 > 基准 × qty × (1+scrap_rate)：出站弹窗黄色提示，不拦截；写批次履历事件 `BOM_OVER_CONSUMPTION`。

## 4. 前端与权限
- 放在产品主数据下的“BOM”标签页：选产品 → 版本列表 → 明细。
- 权限码：`bom:read`、`bom:write`；机台上料：`equipment_mount:read/write`（后端确认）。

## 5. 后续候选（不在首期）
- Cycle Time、Move 报表。
- 光罩与机台上料材料的寿命/使用次数（参照现有 `tool_life` 的模型和进站校验扩展，不另起一套）。
- PM 后放行联动：`pm_complete` 后机台转为“待 Qual”，Qual 通过才可进站（现状：PM 完成只重置周期）。

## 6. 测试要点
见测试评审 5 条：无 BOM 开批、拆合批、返工/报废基准、版本切换不影响在制批、比对提示可在履历查到。

## 7. 后道封测（v0.3）
### 7.1 层级
- 每个 BOM 只有一层；明细可以引用另一个产品（半成品），多级靠这种引用串起来。
- 首期只做两级：晶圆/die 层和封装成品层。测试、包装阶段用产品版本区分，不另加层级。
- 前端：BOM 标签页改成树形，半成品节点只读展开（显示它当前生效的版本），点进去才能维护。

### 7.2 替代料（首期最小版）
- `bom_line_substitute`：bom_line_id、替代物料、优先级。随 BOM 版本一起生效，不单独审批。
- 扣料时先用主料，主料不够或没有时按优先级用替代料，并在用料记录里注明用的是替代料。

### 7.3 扣料方式与批号追溯
- 出站扣料（issue）：die、框架/基板、包装材料。
- 机台上料（mounted）：线卷、粘片胶、塑封料、锡球、助焊剂。
- 以下必须追批号：晶圆（追到晶圆 ID 加 die 坐标）、框架/基板、线材、粘片胶、塑封料、锡球。
- consume_mode 必填，没有默认值。

### 7.4 坐标图（按 E142 的思路，新建表，不改现有的载具槽位图）
- `substrate_map`：基板类型（wafer/strip）、基板 ID、行数、列数、来源（import/eap）。
- `map_cell`：map_id、row、col、bin_code。
- `bin_definition`：bin_code、名称、良品或不良、所属产品或测试程序。
- 首期只做文件导入加表格展示，canvas 图形显示放到下一期。

### 7.5 单位转换事件（核心）
- `unit_transform`：事件 ID、类型（dicing/die_attach/singulation/bin_split 等）、操作人、时间、工步。
- `unit_transform_input`：lot_id、基板 ID、转换前数量。
- `unit_transform_output`：lot_id、新产品、新 track_unit_kind、转换后数量。
- `unit_origin`（位置映射）：child_lot_id、子位置（条号加行列，或颗序号）、parent_lot_id、parent_wafer_id、die 坐标（行列）。
  - 支持多入多出；谱系在现有拆批、合批之外新增 relation_type=transform，`trace.py` 正向、反向都走这张表。
- 规则：
  - 不适用“拆批不能拆完”的规则；母批转完后状态变为“已转换”。
  - 每片晶圆的可用颗数以坐标图里良品 bin 的数量为准；没有导入坐标图时，用产品主数据的 gross die 并给出提示。
  - 每片晶圆的良品颗数、不良颗数和边缘损失必须正好等于总颗数，对不上就拦住。
  - 分到各子批的颗数之和必须等于这片晶圆的良品颗数。
  - 子批锁定它自己产品的 BOM 版本；母批锁定的版本不变。
- 损耗比对的基准：当前工步进站时的良品数。

### 7.6 前端
- 所有数量列都带单位；`track_unit_kind` 和 uom 要补中英日三种语言的名称（i18n key 为 `unit_kind.*` 和 `uom.*`）。
- 批次履历和谱系查询可以顺着 unit_origin 从子批一路查回母晶圆和 die 坐标。

## 8. 分期建议
- **P1（本期）**：BOM（两级、版本、替代料列表）；用料记录补 source 和 usage_type；机台上料记录；单位换算表；坐标图导入加表格展示；单位转换事件和谱系；单位的三语名称。
- **P2**：测试 bin 分档和按 bin 拆批（复用 7.5 的单位转换事件）；测试程序版本（主数据加过站记录）；回温时间（有效期沿用现有逻辑）；die 级晶圆图和条图的 canvas 显示；各工站按颗统计良率和损失；PM 后 Qual 放行联动。
- **P3**：打标规则；湿敏等级（MSL）和烘烤管控；客户级出货追溯；光罩和上料材料寿命；Cycle Time 和 Move 报表。

## 9. 补充（2026-10-14 09:13，采纳设备集成 E1 的意见）
- equipment_material_mount 增加 external_event_id，可为空，按（来源，外部事件号）建唯一约束，EAP 重复上报同一事件时靠它去重。同一个上料口（机台加上料位置）同一时间只能有一条 unmounted_at 为空的记录，即只能装一批料。
- substrate_map 增加 origin_location（坐标原点位置）和 axis_direction（坐标轴方向）两个字段，并关联导入记录 map_import（来源文件或上报来源、导入人、导入时间）。
- bin_definition 增加 bin_set_version，按版本管理。map_cell 的 bin 码必须能在对应版本的 bin 定义中查到。
- 不规定导入文件的格式，由导入适配层转换后写入同一套表。

## 10. 决议补充（v1.1，2026-10-14 09:16，答复测试评审 13 问与后端 8 问）
### 比对与数量
- 损耗比对的基准，前道和后道统一取“该工步进站时的良品数”，单位跟随 per_basis。第 3 节按此理解。
- 超量检查在前道和后道都是只提示、不拦截。
- 数量精度：数量统一存为 Decimal(18,6)，单位换算四舍五入到 6 位小数。计件单位（ea、die、strip、unit、wafer）必须是整数，不是整数就返回 422。
- 主料和替代料都不够时，沿用现有 `consumption.py` 的缺料处理，不允许负库存。BOM 比对不改变扣料逻辑。

### BOM
- 空版本和有版本的批次合批算“版本不同”，拒绝；两个都是空版本可以合。
- 两级限制由后端拦截：激活 BOM 时校验展开深度不超过 2（常量 `MAX_BOM_DEPTH=2`），并检测循环引用。
- 替代料的维护归 `mes.bom:write`。

### 单位转换
- 是一个独立操作，不挂在出站上。母批状态为 WAITING 或 MOVED_IN 才能转换，Hold 中不行。
- 不支持部分转换：只转一部分晶圆的话，先用现有的拆批拆出来，再整批转换。
- 撤销：只有当所有子批都还是 WAITING、而且没有任何后续交易时，才允许撤销。撤销后母批恢复到转换前的状态，坐标图引用释放，写一条撤销事件，权限同 `mes.exec:transform`。
- Q-Time：转换前已经开始计时的 Q-Time，子批继续沿用原来的起点；转换后的新区间按子批的流程重新开始。
- wafer 表标记为 converted。条要建单元记录（有条号）；die 在 P1 不建单元记录，位置靠 unit_origin 表达。
- 子批之间按普通合批规则处理：产品和 BOM 版本一致就可以合。
- 没导入坐标图时，可以人工录入良品数，但必须填原因码，并记一条事件；已导入坐标图时，不允许人工改。
- 边缘损失用 bin 定义中“边缘/不可用”类型的 bin 表示，随坐标图导入，不提供手工录入。

### 坐标图与上料
- 单独建 `mes/map` 模块，不放在 quality 里。
- 导入分两步，先 preview 再 commit：`POST /mes/map/import/preview` 返回逐行报错，`POST /mes/map/import` 提交。
- P1 只做 CSV。坐标原点和轴向写在文件头，数据列为：基板编号、行、列、bin 码。E142 XML 到接 EAP 时再做。
- 同一基板重复导入时生成新版本，旧版本保留。转换和 unit_origin 引用具体版本的 id。
- 上料口已经装着料又来上料：人工录入拒绝（409，并写明当前装的批次）；EAP 上报在同一事务里先卸旧批再装新批。去重用 (tenant, source, external_event_id) 组合唯一，source=eap 时 external_event_id 必填。

### 权限码（以后端草案为准）
`mes.bom:read/write/activate`，`mes.equipment:mount`，`mes.map:import/read/write`，`mes.exec:transform`；单位换算用 `mes.product:*`。成员账号在接口层也写不进去。

## 11. B1 实现确认（2026-10-14 09:37）
- 接受后端实现中与设计不同的 5 处：新增作废接口 `/void`；生效时间自动填当前时间，不支持预约生效；没有明细的 BOM 不能生效；生效时也要校验上层 BOM 的层级和循环引用；`bom_required` 作为检查规则，默认关闭。
- 明细的可选工步：从引用 `route_step` 改为引用工序 `operation_id`。流程改版后不受影响。出站比对时，凡是该工序的工步都会触发比对，比的是截至当前的累计实际用量对比 BOM 计划用量；返工用量不计入。
- BOM 继续挂在产品版本上，保证追溯准确。产品出新版本时，自动把当前生效的 BOM 复制成新产品版本下的草稿，由人工确认后再生效。
- 行号约定：预览报错返回 `row_no`（按数据行计，从 1 开始）和 `file_line`（原始文件行号）。bin 定义的版本取自它自己的文件头；坐标图引用的定义集不存在时，返回 422。
- `bom_required` 检查规则分三档：off 不检查；warn 放行，在 warnings 里返回 `no_active_bom`；block 返回 422 拦截。（对应 D1）
- 生效时由后端自动填写 confirmed_by（当前操作人）和 confirmed_at（当前时间），不接受客户端传值。确认这一步靠 `mes.bom:activate` 权限来把关。
- 创建 BOM 时如果传了 effective_at，返回 422；生效时间只能由 activate 产生。

## 12. 补充决议（2026-10-14 10:17）
- 接口里传了不允许客户端写的字段（route_step_id、effective_at、confirmed_by 等），一律返回 422，不再静默忽略。
- 新产品版本自动复制 BOM 时要检查 `mes.bom:write` 权限；没有这个权限就不复制，并在响应的 warnings 里返回 `bom_copy_skipped`。
- 坐标图和按 bin 拆批的数量守恒：
  - 坐标图层：坐标总数 = 各 bin 数量之和（包括排除类 bin）。
  - 拆批层：子批数量合计 + 排除数量 = 坐标图总数。
  - 哪些 bin 算排除类，由 bin_definition.bin_type 决定（edge/unusable 等），代码里不写死具体 bin 码。
- 时间（对应 D2）：数据库一律用 timestamptz 存储，接口统一输出 ISO 8601 的 UTC 时间（带 Z），由前端转换为本地时间显示。适用于 BOM、上料以及以后的 EAP 接口。
- 「传了只读字段返回 422」的适用范围（10:18 澄清）：只适用于 P1 新增接口（BOM、上料、坐标图、单位转换），已有实体的通用增删改查行为不变，避免引发回归。前端各表单统一只提交可写字段。
- 手工上料（10:20 定）：传 `source`（任何值）返回 422，source 在代码里固定为 manual。`external_event_id` 保留为可选，用来做幂等去重：唯一键是 (source, external_event_id)，同一个 ID 重复提交只记一次并返回 duplicate=true，跟 EAP 上报的 ID 互不冲突。由前端每次打开表单时生成 UUID。
- 第 13 节，B2 评审（见 D31）：换算系数可以用浮点数，换算结果入库前转成 Decimal(18,6) 并四舍五入（ROUND_HALF_UP）。P1 合并前，所有接口的时间都要输出带 Z 的 UTC。
- 第 13 节补充：见 D32（超量只在增加时报警，同一物料的用量按工序归属，动作接口的请求体规则）。
