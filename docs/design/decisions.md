# 已确认决定（kai mi，2026-10-13，全部按架构师建议）

1. 批次 8 个状态保持不变。
2. 加工中批次被 Hold 后允许 Track Out，不允许 Move Out。
3. 加工中批次不能被手动报废，也不能被 Q-Time 超时报废。
4. 终态批次不能被 Hold（含自动 Hold）。
5. 本期不做撤销进站（Abort）。
6. completed（待入库）仍算终态。
7. lot、equipment 加 row_version 列。
8. outbox 保留 30 天。
9. 首批事件加 lot.created、lot.stored。
10. service 内部不提交，改由路由层统一提交；本期做，排在状态机之后。
11. equipment.state_changed 的 trigger 预留取值 equipment（本期不实现）。

## 测试评审 19 处问题的处理（2026-10-13，架构师）

来源：`/workspace/cim-team/qa/test-plans/lot-state-machine-cases.md` §11。P01/P02/P03/P05/P07/P09/P10 等为架构师已定事项，其余按 D1–D11 推导；P15 待 kai mi 定。

| # | 结论 |
|---|---|
| P01 | 因 Hold 被拒沿用错误码 `on_hold`，其余非法状态用 `lot_status`；两者都不满足时先报 `lot_status`。 |
| P02 | 写接口支持可选 `Idempotency-Key`，按租户存 24 小时，同键同请求体重试返回首次结果，同键不同请求体 422，执行中 409；不带键保持现有行为（重复提交 422）。 |
| P03 | Hold 事件 aggregate_type=`lot`，删去 `lot_hold` 取值。 |
| P04 | 每发一个事件 row_version+1；一次动作发多条就加多次（track_out 全报废发 tracked_out + terminated，+2）。 |
| P05 | 终态批次允许 Release（只清遗留 Hold、不改状态），以 SM§4 为准，N05 改为"除 release 外"；hold 不存在 404，已解除 422。 |
| P06 | 每次 hold/release 都发 lot.held / lot.released 并 +1，不论 on_hold 是否变化。 |
| P07 | 事件名统一过去式（lot.moved_in / tracked_in / tracked_out / moved_out 等），以 EV§4 为唯一来源，transition 用 EVENTS 映射；`lot.split` 保留。 |
| P08 | 不发事件的动作（jump/carrier/priority/部分 adjust/部分入库）不加 row_version，E05 严格断言连续。 |
| P09 | undo_start 删除前发 `lot.creation_reverted{lot_code, work_order_id, qty}`。 |
| P10 | `lot.stored` payload 为 lot_id、warehouse_id、location、qty、stored_at；只在满额入库（completed→stored）时发，部分入库不发。 |
| P11 | 自动来源 Hold 终态批次：不抛异常，返回 skipped 并记 warning，不写任何数据或事件；手动来源 422（符合 D4）。 |
| P12 | 拆批子批按现有 `sm_rules.COPY` 继承母批 step、路线和进站设备上下文（moved_in 子批同站）；I2 只约束终态，不受影响。 |
| P13 | 拆批数量须 ≥1 且小于母批数量，拆全部或母批剩 0 → 422 `lot_status`。 |
| P14 | merge 源列表有重复 id 或源包含目标 → 422，不去重静默处理。 |
| P15 | **待 kai mi 定**：报废后遗留的 active Hold 是否自动释放（见下）。 |
| P16 | 锁超时 409 `lot_busy`，等到锁后状态已变 422；并发用例断言 ∈{409,422} 且恰一个成功，409 只计数。 |
| P17 | D10 落地前后行为不同的事务用例用 `xfail(strict=True, reason="待 D10")`，D10 合入时去掉。 |
| P18 | 开批 row_version 0→1，`lot.created` version=1（拆批子批同样）。 |
| P19 | CI 加 PostgreSQL service 跑并发/RLS 用例（测试评审草稿已带）。 |

附加：`equipment.state_changed.trigger` 预留取值 `equipment`（D11，本期不实现）。

### 待 kai mi 定
- **P15 报废后遗留 Hold**：持 Hold 批次被 adjust 报废到 0 后，active Hold 怎么处理？建议**保留不自动释放**（保留 Hold 责任与审计记录，Hold 方仍可按 P05 手动 Release），看板与 Hold 列表默认排除终态批次。替代：报废时自动 release 并记 reason=`lot_scrapped`。定之前后端保持现状（保留），相关用例 xfail。

## 补充（2026-10-13 18:22）
- P15：kai mi 选 A，报废到 0 不自动释放 Hold，保留审计记录；终态批次默认不进看板和 Hold 列表。
- N1：幂等键比较范围 = 租户 + 键 + 方法 + 路径 + 请求体哈希；同一个键用在不同接口返回 422 idempotency_key_reused。
- N2：24 小时按键的创建时间算；查询时过期即视为不存在，清理任务只负责删除，不影响判定。
- N3：P15 已选 A，不适用。
- N4（合批错误码）：合批先对目标和每个源批次走状态机 check()，状态不合法返回 422 lot_status，持 Hold 返回 422 on_hold；状态都合法后再走合批规则检查（产品、工艺、站点一致性等），不满足返回 409 check_blocked。B08、B10 按 422 期望实现。
- N5（错误格式）：所有业务错误统一 `detail: {code, message?, ...}`，code 用 snake_case 名词短语；合批源重复/含目标用 merge_source_invalid；幂等键用 idempotency_key_reused / idempotency_in_progress（idempotency_key_mismatch 已作废，见 D72）。
- N6（18:58 再修订）：Hold 列表默认只排除 scrapped、merged（后端无 shipped 状态）；completed、stored 默认显示；include_terminal=true 显示全部；每条返回 lot_status。

## 工艺评审决定（kai mi，2026-10-13 18:42，全部按建议）
- D12（改 D3 相关的 Q-Time 行为）：Q-Time 超时不再自动报废，改为自动 Hold，原因码 qtime_expired，trigger=qtime，不发 lot.terminated。running 批次仍可 Track Out（B1），持 Hold 不可 Move Out（D2，422 on_hold）。
- D13（修订 D4）：completed、stored 允许手动 Hold（WAT 异常/客诉）；scrapped、merged 禁止。状态机 ship 规则仅 stored，持 Hold 返回 422 on_hold（无接口，出货功能下期定）。
- D14：返工无返工路线时拒绝，422 rework_route_missing。拆子批返工下期。
- D15：M4 按晶圆返工计数（新增 wafer_rework_limit 检查，读 wafer.rework_count，可放行阻断）下期。
- D16：工艺建议 S1–S7 全部下期（S3 中 moved_in 监控部分已由 D19 提前到本期）。
- D17：自动 Hold 与手动 Hold 规则拆开。自动 Hold（qtime、equipment 等 trigger）只作用于 waiting、moved_in、running、tracked_out；遇到 completed、stored、scrapped、merged 时跳过，不抛错、不建 Hold，写一条日志（通知留到下期 S6）。
- D18：qtime_expired 作为系统原因码，由迁移为现有租户补建、新租户初始化时自动创建；查不到时仍退回默认 Hold 原因作兜底。
- D19（kai mi 19:19 已定，本期；D16 中 S3 的 moved_in 监控提前到本期）：本期把 Q-Time 停表点改到 Track In，并把 moved_in 纳入扫描。在制加工时长监控归 EAP 下期。
- D20：Q-Time 超时 Hold 的原因码：规则里配了就用规则的，没配用 qtime_expired；Hold 记录 trigger 一律为 qtime，以 trigger 识别 Q-Time 触发。
- D20 补充（kai mi 19:19 已定，本期）：Q-Time 自动 Hold 记录增加可空字段 qtime_rule_id、qtime_from_step_id、qtime_to_step_id、qtime_overdue_seconds。
- D21：Hold 记录的触发来源字段以代码现有的 source 为准（取值 manual、qtime、equipment 等），文档中 D12、D17、D20 所说的 trigger 指同一字段，不改列名。D11 的 equipment.state_changed.trigger 是事件字段，另当别论。
- D22：Track In（D19 后）遇到已超时批次：转 Hold 并提交，接口返回 200，响应体带 qtime 处置结果（held=true，未进站），与现有 Move In 的行为一致；不返回 422，避免报错导致事务回滚、把 Hold 一起撤销。批次已持 Hold 时再次 Track In 照常返回 422 on_hold。
- D23：Q-Time 管控开关的严重度配置随 D19 本期从 Move In 时机改到 Track In 时机，配迁移把已有配置平移过去（可重复执行、可回滚）。Move In 不再读取这项配置。
- D24：qtime_rule_id 外键保持 RESTRICT，不改成置空，保证 Hold 记录能追溯到规则。删除已被引用的规则返回 409 qtime_rule_in_use，提示改为停用规则。
- D25：Q-Time 规则处置为 hold 时不再强制要求原因码（与 D20 一致：没配就用 qtime_expired），新建、修改、停用都不因缺原因码而 422。配了原因码时仍校验其存在且属于本租户。
- D26（落实 D12，20:22 更正）：Q-Time 规则的处置选项去掉 scrap，保留 warn、hold、rework（warn 只记录提醒、不 Hold，与 D12 不冲突）。已有处置为 scrap 的规则由迁移改成 hold，原因码保留（照 D25 可空）；接口收到 scrap 返回 422 qtime_action_invalid。

- D24 补充（20:26，补 D24 漏项，不算新范围）：qtime_rule 增加 `is_active` 布尔字段，默认 true，迁移时已有规则全部设为 true。停用后不再开始新的计时；Track In 判定和 sweep 都跳过停用规则，包括停用前已经在计时的批次；已经挂上的 Hold 不受影响，照常人工 Release。重新启用只对之后到达起始工步的批次生效，不追溯。

## 下期待办（本期 Q-Time 范围到 D26 收口，新问题记在这里）
- API-01：PATCH 收到未知字段时返回 200 并忽略（`app/core/spec/validate.py` 通用问题，已确认），下期定全局策略，倾向改成 422。
- API-02：校验错误 422 的字段名用了列名（如 `reason_id`），应改用 spec 字段名（如 `reason`），前端提示才能显示正确的字段文案。与 API-01 一起定。
- Q-01：warn 超时本期只在监控里显示；下期写一条批次履历事件（`qtime_warned`，带规则、工步、超时秒数），通知先不做，留给以后接 EAP/OI。
- Q-02：0011 降级只回改仍是 hold 且带迁移标记的规则（改成 rework 的不动），attrs 为 NULL 的降级后保持 NULL。下期优先做。
- Q-03：原始请求校验钩子补通用单测；Excel 导入的行报错只取 message（`excel.py:224-231`）。
- Q-04：单测 `test_qa_01~03` 与用例 QA-01~03 重名，改名。
- FE-01：`rbac/permissions/index.tsx` 过滤状态下图标是展开的，但提示和 aria-label 显示「展开」，改成按 `filtering || expanded` 判断。

## D27（23:08，kai mi 拍板）菜单调整
按 `menu-proposal.md` 最新版做方案 A，并把 MENU-C1 中的菜单搜索（Ctrl/⌘K，中英日都能搜，结果按权限过滤）和顶栏面包屑提前到本期。数量角标、常用区、按角色设首页仍放下期。
本期不加迁移，不收紧接口，不新增后端接口：搜索只用 `/menus/me` 已下发的数据。「投片/开批」暂按方案使用。
D27 补充（23:11）：已有租户的 admin 会在 prestart 时由 `seed_tenant_roles` 补上 `notify:config`，不用加迁移；部署时必须走 prestart。
下期待办 RBAC-01：`seed_tenant_roles` 只增不减，租户自己从默认角色里删掉的权限，每次重启都会被加回来。下期改成只在新建角色或版本升级时补权限，并且记下租户手动去掉过的权限，不再覆盖。
D27 更正（23:12）：admin 原本就有 `notify:config`（模块权限会自动并入 MES_PERMISSIONS），所以不改代码，只补测试；上一条「prestart 补权限」的说法对本项不适用。RBAC-01 不变。
D27 补充（23:27）：消息中心和个人设置「移出侧边栏」整项挪到下期（MENU-C5：菜单数据加「不在侧栏显示」字段，前端侧栏和搜索识别它，路由和权限照旧）。本期这两项保留在工作台分组，前后端都不做半套标记。
下期待办 TEST-01（23:57）：conftest 没设 `TEST_DATABASE_NAME` 时直接报错退出，不再回落到默认库 `app_test`。
下期待办（00:04）：
- DASH-01：本期不算缺陷（QA 检查时刚好跨过 0 点）。下期把「今天」从服务器本地时区改为「业务时区 + 生产日起始时间」：起始时间取自日历与班次，抽成一个公共的生产日计算函数，统计报表和以后的 EAP 事件归日都调用它；补 0 点边界测试和 UTC 部署测试。只改后端。
- FE-02：中文侧栏「Future Hold（预约 Hold）」被截断；英文「Warehouse Management」折成两行；403 页面没有顶栏。
- FE-03（00:17，00:25 补充）：前端 fixture 手工复制后端菜单 key 和 TAB_TITLES（`menu-keys.fixture.ts`、`TAB_ONLY_MENU_KEYS`），容易和后端脱节。下期改为由后端 `export_mes_i18n` 一并导出菜单 key 清单，前端测试直接读取。另外跳转回归测试要把 key 里的下划线换成连字符再比对（例如 `mes-check_rule` 对应 `/mes/check-rule`），并把 `<Kpi to=...>` 这类写法纳入检查。

## D28（09:12，kai mi 确认）BOM 与封测单位转换
- 以 `design/bom.md` v1.0 为准（前道和后道封测都适用），按分期 P1 → P2 → P3 推进，本期只做 P1。任务卡见 `design/bom-p1-tasks.md`。
- 所有分支都从本地 `c1m-main`（`c1a1fd6`）拉出，不推送，也不部署。
- 接口路径、字段名和权限码由后端按现有命名惯例定下后贴到群里，我登记到任务卡；前端在那之前用 mock 开发。
- FE-02 补充：ref-select 测试改用 `getByRole` 找清除按钮 ×；补一条「清除后 × 消失」的测试；仅靠悬停才能看到的全文，要让键盘和读屏用户也能读到。
- AUTH-01（下期）：登录只认用户名，不区分大小写（后端已确认），前端把登录框的提示文字改为「用户名」。

## D29（10:05，kai mi 拍板）P1 加项与 P2 出货
- P1 加入三项：PM 后须通过 Qual 才放行（含已修复的 BUG-PM-01）、测试 bin 分档和按 bin 拆批、客户来料两个字段（客户批号对应、物料归属）。任务卡为 B6–B8 和 F5–F7，见 `bom-p1-tasks.md`。P1 总工作量约 20 人日。
- P2 要对客户出货：包装层级、出货标签、客户级追溯、湿敏等级（MSL）提前到 P2，见 `gap-list.md` v0.3。
- D30 手工上料：拒绝 source（422），external_event_id 可选，作为幂等键，唯一键是 (source, external_event_id)。
- D31 接受 B2 的五处偏差：1) 换算系数可以继续用浮点数，但换算结果入库前要转成 Decimal(18,6)，统一四舍五入（ROUND_HALF_UP）；2) 这期只区分正常和返工；3) 没挂工序的明细在最后一步出站时比对，计划基准就是进站时的良品数，按批计的取 1；4) 子批只累计自己的用量，用量查询接口加 inherited=false 说明；5) 替代料的优先级放到 P2。0016 给 material_consumption 加 external_event_id 是对的。旧接口输出 +08 先记成已知问题，P1 合并前要统一成 UTC。
- D32 B2 和 D4：1) 只有当累计超出量比上次报警时更大，才再报超量；track_out 响应里的 warnings 和批次履历用同一个判断。2) 同一物料的用量按工序归属：在绑定了该物料明细的工序上发生的用量，记到那条明细上；其他工序上的用量，记到没绑工序的那条明细上。超出的部分不挪到别的明细，bom-usage 里要写明这条归属规则。3) activate、void、copy 这三个接口：不带请求体或请求体是 {} 都放行，只要带了任何字段就返回 422。
- D33 接受 B6 的前四处偏差：1) wait_qual 作为机台上的独立字段，不改 E10 状态；2) Qual 不通过时关闭原任务，再生成复测任务；3) 这是内置硬拦截，卡控规则里关不掉；4) 这期只拦主设备，子单元字段预留，见 0018。第 5 处不按建议走：PM 通知的去重键不能依赖时间字符串的格式，改用 PM 计划 ID 加到期时间的 epoch 秒，或者 PM 记录 ID，这样就不会重复发通知。部署检查单里仍然要写一条，提醒核对这项改动。
- D34 P1 新接口先做认证和权限检查（不通过返回 401/403，响应里不带字段明细），再校验请求体（422）。顺带在 B7 里改。凡是由 EAP 写入的那部分，延后到接 EAP 时再测，不算 P1 的阻塞。
- D35 只按批次数计的 PM 计划，去重键用起算点的 epoch 秒。chamber_id 改名为 sub_unit_id，指设备的任意子单元（腔体、主轴、测试头、焊头），这期为空，跟 0019 一起提交。
- D36 B7：接受新增 mes_customer 表，P1 先沿用 mes.lot 的权限。不同客户批号的批次不能合批，返回 422 customer_lot_mismatch，不能强制放行；两边都没有客户批号的可以合。下一个迁移给 (tenant_id, customer_lot_no) 加普通索引。其余偏差（D34 扩大到通用接口、重复执行 0018、开批接口用宽松载荷、单位转换复用 inherit_customer）都接受。
- D37 客户批号：入库时只去掉首尾空格，保存原样；查询和合批比对都忽略大小写（统一转成大写再比），按大写做精确匹配，不做模糊查询。0020 的索引改成建在 (tenant_id, upper(customer_lot_no)) 上。
- D38 开批接口的所有报错路径统一用 Pydantic 的数组写法，序号从 0 开始（如 ["body","lots",0,"qty"]）。前端同步修改解析。
- D39 B4：接受 6 处偏差（JSON 传 CSV 文本，请求体上限 10MB，超过返回 413；rows/cols 取文件里的最大行列号；基板类型只有 wafer/strip；bin_type 四类；bin 定义集暂不关联产品或测试程序；EAP 写入入口不做）。坐标图加 3 个可空字段 lot_id、equipment_id、operation_id，手工导入时选填；lot_id 不传时，按基板编号找到它当前所在的批次（片位记录）自动关联，找不到就留空。用单独的迁移在 B8 之前加。版本号冲突返回 409 map_version_conflict。
- D40 开批接口改成严格载荷：请求体顶层只接受 lots，每个批次只接受 qty、carrier_id、slots、source_ref、customer_lot_no、ownership、customer_id，未知字段（包括旧的 carrier）返回 422。原因：静默丢掉字段会导致载具没绑定。单独出一个小提交，上线检查单里要提醒外部调用方。
- D41 B5：1) 子批必须显式给 route_id，接受。2) Q-Time 必须带到子批，沿用母批的起算时间（bom.md §10），这处偏差不接受，跟 B8 一起改。3) 撤销延到 P2，P1 转换前预览就是主要的防错手段。开批接口把 wafer_sources 加回严格载荷的白名单，用于晶圆级来料追溯。新增前端卡片 F8「单位转换操作页」，放在 F4 后面。迁移一律显式指定库。
- D42 B8：五处偏差都接受（B8 不给 route_id 时子批留在当前工步；按坐标图版本选取的规则同步到 B5；撤销放到 P2）。P1 不开放指定 map_version，预览响应要返回每片晶圆实际用的 substrate_map_id 和 map_version，让操作员能确认。要不要能按指定版本拆批，放进 P2，等工艺专家确认。

## D43 上料不受 PM/待 Qual 状态拦截（2026-10-14）
- 机台在 PM 或 qual_state=wait_qual 时，上料/卸料照常允许（200），不加 equipment_not_ready。
- 理由：PM 期间换耗材、Qual 跑片都要用料；风险在未放行机台跑正式批。
- 拦截点在开工：Move In/Track In 由 B6 返回 409 check_blocked / eqp_wait_qual，overridable=false。

## D44 老接口严格校验延到 P2（2026-10-14）
- Move In / Track In 等老接口继续忽略未知字段，P1 不改（§12 严格校验仅限 P1 新接口）。
- P2：先记录老接口收到的未知字段日志，确认无调用方传入后再收紧为 422。
- force/override 不影响 eqp_wait_qual 硬拦截（已验证）。
- P2 日志需同时记录调用来源（source、客户端标识）。

## D45 时间输出防回退（2026-10-14）
- 数据库会话时区不改（保留报表按本地日期分组）。
- 新接口优先声明 response_model，用 UtcDateTime 类型；必须返回 dict 或声明 `-> Any` 时，时间一律经 iso_utc。评审时检查。
- 全量 GET 扫描测试固定在 TZ=Asia/Taipei 下跑，作为 CI 兜底；出现非 Z 偏移即失败。

## D46 导出 xlsx 的时间格式（2026-10-14）
- P1：保持 UTC 的 Z 文本（ISO 定长，按文本排序即按时间排序）。
- P2：改为 Excel 日期单元格，按租户时区换算，列名标注时区（如「创建时间 (UTC+8)」）；接口 JSON 仍为 UTC Z。

## D47 两级 BOM 与循环引用的校验点（2026-10-14）
- 编辑草稿（整单/逐行）：422 bom_cycle / bom_depth_exceeded，路径指向 component_product_id；属提前提示。
- 生效（activate）是最终把关，必须再查两个方向：
  1) 本版本引用的半成品，其生效 BOM 不得含半成品行；
  2) 若本版本含半成品行，则不得有任何生效 BOM 引用本产品（否则引用方变三级）；且不得形成循环。
- 生效失败返回 409（请求体为空，不用 422），code 为 bom_cycle 或 bom_depth_exceeded，details 列出相关产品编码与版本。

## D48 半成品必须有生效 BOM（2026-10-14，补 D47）
- 生效时：引用的半成品若无生效 BOM，返回 409 bom_component_no_active，details 同 D47 格式；编辑时仅提示不拦。
- 作废时：若本 BOM 是该产品唯一生效版本且被其他生效 BOM 引用，返回 409 bom_referenced，details 列出引用方。被新版本取代不受影响。
- 编辑时只看生效 BOM、草稿互引到生效时才拦、编辑时不查被引用方：均接受（生效为最终把关）。
- PATCH 只有改到 component_type / material_id / component_product_id 时才重跑结构校验。

## D49 BOM 用量输入精度（2026-10-14）
- 用户录入的主数据不静默舍入：qty 最多 6 位小数，scrap_rate 最多 4 位小数（0 到 1 之间的比例），超出返回 422 `too_many_decimals`，路径指向该字段。
- D31 的 ROUND_HALF_UP 只用于计算结果（换算、计划用量），不用于录入值。
- 若数据库列精度与此不符，以本条为准调整列或校验。
- 判断位数前先去掉末尾的零（"1.5000000" 按 1 位）；科学计数法按换算后的十进制值判断；scrap_rate 允许 0 和 1，小于 0 或大于 1 返回 422；qty 必须大于 0。

## D50 P1 十进制数值按字符串返回（2026-10-14）
- 范围：P1 新接口里的 Decimal 字段（BOM qty/scrap_rate、单位换算 factor、用料与计划用量、单位转换数量）按十进制字符串返回。
- 格式：定点写法，不用科学计数法，去掉末尾的零（"1.5"、"0.015"、"2"）。
- 老接口不改（同 §12、D44 的兼容考虑），P2 再评估。
- 输入同时接受字符串和 JSON 数字（D49）。

## D51 P2/P3 并行规则（2026-10-14，kai mi 定）
- 目标是 P1、P2、P3 全部完成。谁手上的活先做完就往下做：空闲即领 P2 的卡（见 `design/p2-tasks.md`），P2 没有可领的卡再领 P3 的。
- P2、P3 在独立本地分支开发：`be/p2`、`fe/p2`、`eap/p2`、`qa/p2`，P3 同理（`be/p3` 等），从 P1 当前本地提交拉出，不影响 P1 合并。P1 合并后各分支再 rebase 或合入，由各自负责。
- P1 的缺陷和复测优先，随时中断 P2/P3 的工作。
- 推送和部署照旧，必须先经 kai mi 批准。
- 各自在群里认领卡片，架构师登记到任务卡；认领前不重复开工同一张卡。
- 设备对接暂停期间，设备集成只领不连真实设备的卡（数据模型、模拟器设计、评审）。
- P3 范围待 kai mi 定方向，架构师先出草案。
- map_version 指定拆批（D42）待工艺专家确认，不分配。

## D52 客户来料批的客户批号必填（2026-10-14）
- 开批时归属为客户来料（customer），customer_lot 必填，去首尾空格后为空返回 422 `customer_lot_required`；自有批不变。
- 只约束新开批，已有空值的历史数据不回填、不报错。
- 后端放进 P1 修复；前端在开批表单加必填校验。原因：客户批号是出货标签和客户级追溯（P2-B2/B4）的主键，缺了无法回溯给客户。


## D53 报警码、耗材寿命、模拟器（2026-10-14，回设备集成 E1–E3）
1. 报警码按设备类型定义；P2 不加型号字段。
2. 未登记的 ALID：只记录（`mes_alarm_log` 里标 `unregistered=true`），不自动 Hold；列表可筛出来给维护补登记。
3. 报警联动产生的设备状态事件 `trigger=equipment`；`auto` 留给系统规则（比如寿命到期）。
4. 模拟器写入的数据 `source=simulator`，跟真实 `eap` 区分开；除此之外的报文和真实设备一致。
5. 耗材复用现有 `tool_status`，P2 不加新枚举值；「到期」由 `usage_count >= max_usage` 算出来，走开工检查 409 `check_blocked`，检查项 `tool_life`：超过上限 `overridable=false`（同 D43 `eqp_wait_qual`），预警或宽限区间 `overridable=true`。不新增错误码。
6. 寿命到期在 P2 只拦开工、发通知，不自动生成更换或 PM 工单（放到 P3 评估）。
7. 模拟器代码放 `eap/p2` 分支的独立目录 `tools/simulator/`，不进后端包；实现另开卡 P2-E5，6 人日，归设备集成。
- 同意 E2 扩展现有 tool/fixture，不建 `mes_consumable`。报警关联批次用子表 `mes_alarm_lot`，原始上报存 `raw` 列。`usage_count`/`max_usage` 改 numeric(18,6)，按片数、颗数计数的修正并入 B10，单独测。
- 待工艺专家确认：哪些报警清除后必须过 Qual、超寿命是否硬拦、touchdown 怎么换算。确认之前默认：都不需要 Qual、超寿命硬拦（不能放行）、touchdown 按每颗计 1。


## D50 补充（2026-10-14）
- D50 范围包括：bom-usage 顶层 `basis`，以及出站响应里 P1 新增的 `bom_usage` 和 `warnings` 中的数量，都返回定点字符串。出站响应的老字段不改。
- 编辑 BOM 时的提示只在前端显示，接口不加 `warnings` 字段（D47 的编辑期检查只返回 422）。


## D54 EAP 写入入口、撤销记录、寿命边界（2026-10-14）
1. P2 新增 EAP 写入入口 `POST /mes/eap/events`（新卡 P2-B11，3 人日，后端）。只有服务账号能调用，权限 `mes.eap:write`。请求体带 `source`（`eap` 或 `simulator`）、`external_event_id` 和事件类型（E10 状态变化、报警、工具计数）。幂等键是 (tenant, source, external_event_id)。手工接口继续按 D30 不收 `source`。入口建好之前，模拟器走手工接口，数据记成 `manual`，靠 `Idempotency-Key` 防重复，D53-4 等 B11 完成后生效。
2. 撤销转换时保留转换记录，标记 `undone_at`、`undone_by`、`undo_reason`，需要加迁移。子批和谱系照 B6 删除，追溯时看得到「曾转换、已撤销」。
3. 撤销不恢复载具，在履历里注明，P3 再评估是否在转换时记录原载具。
4. 时区：没有租户时区之前，取第一个启用 site 的时区，没有就用 Asia/Taipei。xlsx 列头写 IANA 时区名，比如 `start_at (Asia/Taipei)`；D46 里的示例以这个为准。
5. 寿命边界：`usage_count >= max_usage` 硬拦（`overridable=false`）。预警区间是 `max_usage × warn_ratio` 到上限之间，`warn_ratio` 按工具配置，默认 0.9，`overridable=true`。
6. 寿命到期在 P2 只要求产生 `tool.life_reached` 事件并写入履历，验收不要求真的推送通知。
7. 模拟器端口改白名单：环境变量 `SIM_ALLOWED_PORTS` 显式列出允许的端口，默认全部拒绝；场景的 target 可以用参数改。


## D55 报警事件细则（2026-10-14，回测试 OQ-2/3/5）
1. 设备事件时间（`set_at`、`clear_at`、E10 的 `event_at`）晚于服务器时间超过 5 分钟，返回 422 `time_in_future`。这个错误码正式登记；5 分钟以内照收。
2. 未登记的 ALID 也写 `mes_alarm_lot`，记录当时的在制批，供追溯；只是不 Hold、不改 E10。
3. 乱序和重放：
   - 没有对应 active 报警时收到 clear：返回 200，不改任何状态，也不新建记录，响应里 `cleared=false`。
   - 对已经清除的报警再次 set：算一次新发生，新建一条报警记录，照常联动。
   - 同一个 clear 重放：返回原记录，200，没有任何变化。


## D56 子批编号、出站 consumed（2026-10-14）
1. 子批号和晶圆号相同（如 FX1072.01）在 P1 不改，避免回归前改编号规则。P2 定新规则，草案是 `{母批}-{bin_code}-{序号}`，要等工艺专家确认；只用于新生成的子批，已有批号不改。
2. 出站响应里的 `consumed` 是 P1 之前就有的老字段，按 D50 不改，仍返回数字。


## D54-5 修订（2026-10-14）
- 进入预警区间（`max_usage × warn_ratio` 到上限之间）时，进站返回 200，警告写进检查记录和批次履历，不要求人工放行。只有用量达到上限（`>=`）时，`track_in` 才返回 409 `check_blocked`，检查项 `tool_life`，`overridable=false`。以 B10 `d27b700` 的实现为准。

## D57 Idempotency-Key 复用（2026-10-14）
- 适用于 E10 手工接口（#IK01）和 B11 `POST /mes/eap/events`。
- 同一个 Key、请求内容相同：返回原记录（原状态码），不校验状态，不写新履历。
- 同一个 Key、请求内容不同：返回 422 `idempotency_key_reused`，不写入。请求内容用规范化后的请求体哈希比较。
- Key 的作用域是 (tenant, 接口, Key)，保留 24 小时。B11 仍按 D54 用 (tenant, source, external_event_id) 去重，内容不一致时同样返回 422 `idempotency_key_reused`。

## D58 报警不单独做进站检查（2026-10-14）
- P2 不新增 `equipment_alarm_active` 检查项。报警对进站的影响只走设备状态：报警引起的状态事件（trigger=equipment）把设备切到 UDT 等不可生产状态后，由现有的设备状态检查拦截。
- 报警本身（含未登记 ALID）只记录、关联批次，不 Hold、不拦进站。
- 按报警等级拦进站等需求，待工艺专家确认后放到 P3。
- B11 去重键仍为 (tenant, source, external_event_id)，tenant 不能省略。

## D58 补充（2026-10-14）
- 下层记录的 `source` 写事件来源（`eap`/`simulator`/`manual`），不写 `equipment`。E10 状态履历加 `trigger`（manual/equipment/system），接口返回带出。
- 报警码可选配置一次状态切换，默认不切；报警一律不 Hold 批次。
- 手工报警接口同一 `external_event_id` 换内容重发：422 `idempotency_key_reused`（按 D57）。
- B6 409 `transform_undo_blocked` 顶层加 `reason`：`already_undone` / `lots_blocked`。
- 排期：D58 对齐提交优先于菜单 key 导出（它阻塞测试和模拟器）。

## D59 报警码联动字段（2026-10-14）
- 联动字段只有 `none`（默认）和 `set_state`；`set_state` 必填 `target_state`，必须是已存在的状态编码，否则 422。
- `none` 带 `target_state` 返回 422（严格，不静默忽略）。
- 迁移：`hold_lot`→`none`；`hold_equipment`/`hold_both`→`set_state`+UDT。downgrade 按 `none`→`hold_lot`、`set_state`→`hold_equipment` 回退，属有损回退，可接受。
- 报警触发的切换不符合迁移表时：报警照常记录，不切状态，返回 200 并带 `state_changed=false` 和 `state_skip_reason`，写日志；整个请求不失败。

## D60 小数位与撤销追溯（2026-10-14）
- 定点数字段（含工具 `max_usage`、用量等 numeric(18,6)）超过 6 位小数返回 422 `too_many_decimals`，不四舍五入；后端单元测试按此改。
- 追溯默认显示已撤销的转换步骤，标「已撤销」并带 `undone_at`/`undone_by`/`undo_reason`；追溯接口在转换节点上返回 `undone=true` 及这三个字段。撤销后的批次关系以当前状态为准，撤销步骤只做展示，不参与谱系计算。

## D61 子批编号修订与打标规则（2026-10-14，依据工艺专家 process/reviews/marking-rules.md，属推断，以客户打标规格书为准）
- 修订 D56 的 P2 草案：子批号 `{根批号}-{序号}`，序号 3 位、不复用；二次拆批仍基于根批号续编，不嵌套；bin 作为批次属性存储，不编进批号。P1 的子批号=晶圆号规则不变。
- 打标（P3）：
  - 模板按「产品+客户」定义，版本管理+审批；字段：型号、日期码 YYWW（取哪个日期可配置）、短追溯码、可选 bin。
  - 打标是路线上的普通工步，工步挂模板；模板含 bin 时校验工步排在按 bin 拆批之后；打标后检验，不合格重打或报废。
  - 发号：系统统一发号，范围「客户+产品+日期码」唯一，不复用，重打沿用原号，发号加行锁。
  - 追溯：记录模板版本、实际内容、机台、人员、时间；追溯码可反查批次/谱系/晶圆；出货标签内容须与打标一致。
- D59 澄清（2026-10-14）：迁移 0029 中 `hold_equipment`/`hold_both`→`set_state` 时，保留报警码原有目标状态；原来没有的才默认 UDT。

## D62 光罩模型、CT/Move、人员资质（2026-10-14，工艺口径待工艺专家确认）
- 光罩：状态沿用 `asset_status`（加 inspecting、pending_maintenance），不用 tool_status；新检查项 `reticle` 替换 `reticle_available`，迁移时把工步上已有配置改过去。
- Move：一次出站算 1 move（按批），`move_qty` 为出站片数；拆批/合批/跳站不算，返工出站算（明细带 rework 标记）。
- CT：本工序 = 上一工序出站（首工序为开批）到本工序出站，按出站日期归日；P3 不扣 Hold。
- 按日分组用站点时区（同 D54 导出规则）；日期跨度上限 92 天，超出 422 `date_range_too_large`。
- 提供 p50/p90 和 wip_lots；路径 `GET /api/v1/mes/exec/reports/ct-move`、权限 `mes.exec:read`、菜单 key `mes-ct-move-report` 照前端稿。
- 资质：预警天数由后端设置下发（默认 30）；不通过硬拦 409 `check_blocked`，overridable=false；「工序+设备类型」优先于「只按工序」；`expires_on` 当天仍有效（站点时区）。
- 做即将到期人员汇总接口；资质履历 P3 做（P3-B6），考核记录不做。

## D63 光罩与 CT/Move 工艺口径（2026-10-14，依据 process/reviews/p3-reticle-ctmove.md，推断）
- 光罩适用关系表 `mes_reticle_applicability`（光罩↔产品+层）；`reticle` 检查按此表校验，不再要求 product_id 相同。
- 寿命按 shot 计，P3 按片折算：shots_per_wafer 挂在「产品+层」上，缺省取光罩默认值；EAP 上报实际 shot 时优先用实际值。记录挂载次数。
- 检查触发：shot 数或天数先到者（可配置）；清洗/修复回来、碰撞、长期存放后置 `inspection_required=true`，首用前须检查。
- 检查不合格：光罩 Hold→清洗→复检；复检仍不合格送修或报废；发 `reticle.inspection_failed` 事件，附自上次合格检查以来曝光过的批次清单。
- 检查到期/待检：硬拦 409 `check_blocked`，overridable=true（需权限，记录原因和人员）。修订 D62 的「只预警」。寿命到上限硬拦不可放行（不变）。
- CT/Move 补充 D62：同时给批次 move 数和晶圆 move 数；返工 move 单列，不计产出效率；另列 Hold 时长；子批 CT 起点继承母批上次出站时间，合批取各源批最早时间。

## D64 P3 字段名与零散规则（2026-10-14）
- CT/Move 字段：`moves`、`move_qty`、`rework_moves`、`rework_move_qty`（不计入前两者）、`hold_hours`（字符串，无数据 null）。
- 光罩：`mount_count`；`reticle.inspection_failed.exposed_lots[]`；放行权限 `mes.reticle:override`；长期存放默认 90 天（可配置）；碰撞 P3 人工录入，预留 `source`（manual/eap）。
- 从未检查合格的光罩，受影响批次从入库/首次启用算起；重复添加同一适用关系幂等 200；不合格后必须清洗再复检，不提供跳过。
- 所有进站检查：`reasons[]` 任一不可放行则整体 overridable=false；保留 `reason` 为第一条。
- 即将到期资质汇总：`GET /api/v1/mes/exec/operator-qual/expiring?days=`，权限沿用现有 operator_qual 读权限，days 缺省取后端设置（默认 30）。
- D64 补充（光罩 v0.3）：同意设备集成第 7 条小点；`shots_per_wafer` 先取「产品+层」，再取光罩默认值，两者都没有时进站 409 `check_blocked`（reason `reticle_config_missing`，不可放行）；无适用关系报 `not_applicable`；挂载不可用光罩 409 `reticle_unavailable`；未挂载只报 `not_mounted`；碰撞录入后置 inspection_required 并自动 Hold。
- D64 补充 2：`reticle_config_missing` 两种 count_basis 都在进站时检查。count_basis=eap 时，若出站前没收到 EAP 的 shot 数，出站按片折算计数（记 `estimated=true`），EAP 后到的实际值按 D57 去重后覆盖修正。
- D64 补充 3：估算修正按后端方案（改写 estimated 记录、补差额、到上限发 life_reached、已出站不回拦）。匹配：同（光罩、批次、工步）有多条未修正记录时取最早一条；找不到时实际值另记一条，不丢。差额为负时累计往下减，但已进入不可用的光罩不自动恢复，须有 `mes.reticle:override` 的人工恢复并记原因。
- D64 补充 4（N-G）：碰撞导致的 Hold 允许直接检查（hold→inspecting 仅限 hold 原因为 incident）；检查不合格再走 Hold→清洗→复检。「不跳过清洗」只针对检查不合格后的流程。
- D64 补充 5：确认后端 hold_hours 按出站批次平均、汇总接口形状（不含已过期）、warn_days 放 operator_qual 元数据；确认光罩 hold_reason 叠加时按 inspection_failed > incident > manual 取更严格者并记履历。

### D59 补充（2026-10-14）
- `state_skip_reason` 改为错误码枚举：`unknown_state`、`already_in_state`、`transition_not_allowed`；新增码须登记到本条。
- 报警履历返回 `state_changed`、`state_skip_reason`。B11、人工报警接口、样例文档同步。
- 菜单键导出 JSON 作为仓库文件提交，附一致性测试。
- B6 撤销 409：顶层 `reason` 仍为 `already_undone`、`lots_blocked`（不变）。`lots_blocked` 时 `lots[]` 每行带 `lot_id`、`lot_code`、`reason`；行级 `reason` 取值含 `referenced`（子批被外键引用，附 `tables[]`）及子批状态不允许撤销类原因（后端提交时列出具体码）。新增行级码须先在 D58 补充登记。
- 枚举名统一：E10 履历 `trigger` 字段的枚举名为 `e10_history_trigger`（取值 manual/equipment/system 不变）；全局枚举名不得重复，后端加测试保证。
- P2-D3：`tool_life` 检查无论来自规则还是内置，`overridable` 一律为 `false`。

### OQ-20 决定（2026-10-14）
- 0029 迁移不失败。租户无 UDT 且未配目标的 hold_equipment/hold_both 转为 `none` 时，每个报警码打一条 WARNING 日志（租户、报警码、原联动方式）。
- 报警码新增字段 `migration_note`：text，可空，只读（仅迁移写入；接口写它返回 422）。内容格式 `"0029: was <原值>, no UDT state"`。
- 报警码之后被改为 `set_state` 时自动清空 `migration_note`。
- 列表支持筛选 `?has_migration_note=true`。降级时丢弃该字段。
- B6 `lots[].reason` 定稿：`lot_status`、`on_hold`、`has_transactions`、`has_descendants`、`parent_status`、`referenced`（附 `tables[]`）。前四个同时命中按此顺序只报第一个。示例见后端 `p2-b6-undo-examples.md`。
- D60 补充：字段元数据 `decimal_places`（定点小数字段的位数，普通浮点字段为 null）；测量值、规格限等浮点字段不受 6 位限制。只读字段写入返回 422 `read_only_field`。

### D65（2026-10-14）
- 422 固定码新增 `unknown_field`（请求体含未知或已删除字段），格式同 `read_only_field`，`loc` 指到具体字段。查询参数校验错误的 `loc` 必须以 `query` 开头。
- `eap_service` 角色追加只读权限：设备、报警码、E10 状态三个实体的 `:read`（列表与详情）。不给写权限，不给其他主数据；EAP 账号不得挂 admin。需要更多实体时先登记到本条。
- D65 补充：`eap_service` 的只读权限名为 `mes.eap:read_master`（服务账号专用，不授予 owner/admin），仅覆盖 `equipment`、`alarm_code`、`e10_state` 的通用列表与详情；导出、树、distinct、写操作仍需模块权限。由 `initial_data` 补齐，无迁移。所有 422 的 `detail` 一律为列表。
- D65 补充 2：422 `loc` 首段按参数来源取 `body`/`query`/`path`。所有 422（含 pydantic 原生）每条都带 `code`；无专用码时 `code` 取 `type` 的值。`timezone_required` 登记为固定码。
- `GET /mes/_meta` 对所有已登录用户开放（只含字段定义与枚举选项，不含业务数据）；不得在 `_meta` 里放业务数据或租户敏感配置。
- D65 补充 3：登记 422 固定码 `date_range_too_large`(ctx.max_days)、`date_range_invalid`、`timezone_required`、`unknown_columns`(ctx.columns)、`no_conversion_path`(ctx.from_uom,to_uom)、`ref_not_found`(ctx.entity)、`enum`(ctx.expected)、`step_ids_mismatch`、`not_text_filter`(ctx.field)、`value_error`；`extra_forbidden` 映射为 `code: unknown_field`。
- 「422 detail 一律为列表」收窄为：参数/字段校验类 422。已定稿的业务对象格式 422（批次状态类、`bin_set_invalid`、`map_qty_mismatch`、`rework_route_missing`、`merge_source_invalid`、Excel 导入 `{message, errors[]}`、配置接口）保持原格式不改，但必须带 `code`。新增业务 422 默认用列表格式。
- D65 补充 4：D57 `idempotency_key_reused` 的 `{code, message}` 对象格式列入保留清单。所有请求体（通用 CRUD 与自定义 EAP/执行接口）一律拒收未知字段，返回 422 `unknown_field`。
- 补充 4 覆盖并取代 D38 中「仅新实体严格校验」：老实体同样拒收未知字段。顺序：前端先改成只发 `_meta` 可写字段并给出提交号，后端老实体严格化再落地；两者同轮测试。
- 补充 4 例外：`POST /mes/eap/events` 信封允许多余顶层字段（D54 需要合并进 payload）；这是唯一例外，新增例外须先登记。带版本实体新建时可传 `version`。

### D66 光罩模型 v0.6 定稿项（2026-10-14）
- Q12：寿命复位后后端置 `inspection_required=true`。
- Q13：事故表 `source` 复用 `alarm_source`（eap/simulator/manual）。
- Q14：`POST /mes/reticle/{id}/restore`，StrictBody，`reason` 必填，权限 `mes.reticle:override`；恢复后后端置 `inspection_required=true`，请求体不得传。
- Q15：光罩状态改用专用枚举 `reticle_status`，修订 D62 中「光罩使用 `asset_status`」；`asset_status` 不加光罩专有值。
- Q16：`reticle_usage_kind` 取值 `report`/`adjust`，与 `tool_usage_kind` 一致；负增量为 `adjust` 且必须带 `reason_id`。

## D67 光罩 v0.6 评审收口（2026-10-14）
- 事故登记接口纳入 D57 幂等范围：重放时用原状态码返回原记录，不加 `duplicate` 字段。
- `repairing` 不加，维修用 D62 的 `pending_maintenance`。
- `eap_service` 在 P3 不加写权限，等真接设备时再登记到 D65。
- restore 只需要 `mes.reticle:override`。已到寿命上限时返回 409 `life_limit_reached`。restore 写状态履历，并发 `reticle.restored` 事件。
- 人工调整计数接口 `POST /mes/reticle/{id}/usage` 按后端方案。`status_code` 设为只读，状态只能通过 hold/release/restore 动作接口改。
- Hold 不叠加：已在 on_hold 时再 hold 返回 409 `invalid_transition`。release 不接受目标状态参数：incident 类回到 inspecting，其他回到 hold 前的状态（由后端记录 `status_before_hold`）。
- D67 补充：原来的叠加规则（inspection_failed > incident > manual）继续有效。「不叠加」只针对人工：已经是 on_hold 时人工再 hold 返回 409 `invalid_transition`。系统触发的 Hold（事故、检查不合格）在 on_hold 状态下，如果比当前原因更严，就把 `hold_reason` 升级过去，状态保持 on_hold，`status_before_hold` 不变，同时写履历、发事件；不比当前原因严的只记录事故，原因不变。release 按最终的 `hold_reason` 决定去向：incident 进 inspecting，inspection_failed 进 pending_maintenance，manual 回到 `status_before_hold`。

## D68 光罩 v0.7 小问题（2026-10-14）
- Q17：枚举值用 `on_hold`，跟 D67 和批次状态保持一致。
- Q18：光罩在 in_use 时被 Hold，要同时卸载并解除挂载。这种情况 `status_before_hold` 记为 available，所以 manual 类 release 后回到 available。
- Q19：动作接口路径按后端方案，统一为 `POST /mes/reticle/{id}/<动作>`：clean-start、clean-complete、repair-complete、inspect-start、scrap{reason}、life-reset{reason}，请求体全部严格校验。scrap 和 life-reset 需要 `mes.reticle:override`，其他动作需要 `mes.reticle:write`。
- Q20：碰撞在任何非 scrapped 状态下都进 Hold（incident）并置待检，`status_before_hold` 记录当时的状态。release 规则不变。
- Q21：单独建 `reticle_usage_kind`，不复用工具的枚举。
- Q22：按 tools.py 的逻辑，增量为正记 `report`，为负记 `adjust`，人工还是 EAP 看 `source`。
- D68 补充：
  - `reticle_status` 是新枚举，终态叫 `scrapped`，不用 `retired`。
  - 光罩在用时碰撞，先卸载，`status_before_hold` 记为 available（跟 Q18 同一规则）。
  - life-reset 的请求体维持 `{reason}`。
  - 用量接口纳入 D57 幂等：重放时用原状态码返回原记录，光罩不带 `duplicate` 字段，工具接口原有的 `duplicate` 保持不变。
  - 补登记事件：mounted、unmounted、life_reached、inspected、inspection_failed、scrapped。clean-start、clean-complete、repair-complete、inspect-start 统一发 `reticle.status_changed {from,to,action}`。
  - 数值列用 numeric(18,6)，时间列用 UtcDateTime，新表都要有 `mes_` 前缀、`tenant_id` 和 RLS。

## D69 光罩剩余问题（2026-10-14）
- Q1：唯一键是 `(tenant_id, reticle_code)`，`revision` 只作普通属性，不进唯一键。换版就是一块新光罩，用新编码。
- Q4：P3 不做 stocker 主数据，库位用文本字段 `storage_location`，最长 64。
- Q7：跨机台重复挂载一律拒绝，返回 409 `already_mounted`。
- Q8：P3 不按机台类型限制挂载。
- Q10：检查记录不单独设权限，录入用 `mes.reticle:write`，查看用 `mes.reticle:read`。
- D69 补充：
  - 唯一键写作 `(tenant_id, code)`。
  - 光罩还挂着（有未关闭的挂载记录）时，restore、life-reset、repair-complete、inspect-start、clean-start 一律返回 409 `still_mounted`。
  - 状态不是 in_use 时卸载，只关闭挂载记录，不改状态，照常发 `reticle.unmounted`。
  - scrap 时会顺带卸载，但只发 `reticle.scrapped`，payload 带上 `equipment_id` 和卸载时的 shots。
  - life-reset 的 `reason` 存进 `comment`，`reason_id` 留空。restore 和 scrap 的 `reason` 存在状态履历的 `reason` 列。
  - 光罩状态不是 in_use/available 时进站，按已有的阻断码拦下。
- D69 补充 2：新增 `mes_reticle_status_log`（from/to/action/reason/actor/at，带 tenant_id 和 RLS），光罩新表共 6 张，`audit_log` 照常写。规格以 v0.8.2 `50b1db2` 为准。

## D70 B8 报警拦进站的工程默认（2026-10-14，开放问题 3 的工程解）
- 不在代码里写死等级划分。每个报警码新增配置字段 `track_in_action`（off/warn/block），默认 off，所有设备类型都适用，不按类型硬编码。
- 机台上有未清除的报警时，取其中最严的 `track_in_action`：block 返回 409 `check_blocked`，原因是 `alarm_severity`，overridable=false；warn 返回 200 并带警告；off 不参与判断。
- 未登记的 ALID 不参与判断。报警清除后立即放行。全程不 Hold 批次。
- 哪些报警码配成 warn 或 block，由工艺专家给出建议的初始数据，只改数据，不改代码。
- D70 补充：
  - 拦截对所有工步默认生效，工步上不单独配置，跟 D58 一致。
  - warn 时沿用进站响应里现有的 warnings[]（同 D54-5），每条 `{code: alarm_severity, ctx.alarms[]}`，alarms 的结构跟 block 一样，多条 warn 全部列出。
  - 设备类型层的 `track_in_action` 非空，默认 off，传 null 返回 422。单台设备覆盖层可以为空，null 表示继承设备类型层。
  - block 时的 `ctx.alarms[]`、`effective_track_in_action`、通过 PATCH 修改，都按后端方案。

## D71 B4 第一批与 P2 遗留（2026-10-14）
- 状态履历表的列名用 username 和 at，可以。
- outbox 落地前，领域事件先记在 audit_log（action=事件名，changes=payload），payload 字段以 domain-events.md 为准，以后迁到 outbox 不改字段。
- 409 的判断顺序：先 invalid_transition（当前状态本身就不允许这个动作），再 still_mounted。
- 检查结果 pass 只能从 inspecting 进来，fail 可以从 inspecting 或 on_hold 进来，可以。
- 超过 6 位小数时，422 的 code 用 value_error，ctx 里带 max_places=6。
- O-1：不要求合并返回。请求体里有未知字段时先报 unknown_field，就足够了。
- O-2：自定义的 int_parsing 条目补上 `input`，跟原生错误保持一致，放进下一个小提交，不单独开卡。
- D71 补充：
  - 检查录入纳入 D57，只支持 Idempotency-Key。P3 不加 source/external_event_id，等以后设备能自动上报检查结果时再加。
  - `disposition` 不传时默认 `none`，列设为非空。

## D72 B4 的 P3-E2 评审收口（2026-10-14）
- scrapped 状态的光罩，usage 和检查录入一律返回 409 `invalid_transition`，也不发 life_reached。
- H-1：跟工具接口一起修，单独出一个提交，按后端方案（先占位存档，跟业务写入同一个事务）。同一个 key 但请求内容不同时，按 D57 原文（第 229 行）沿用 422 `idempotency_key_reused`，不新增 mismatch 码。原请求还没完成时，返回 409 `idempotency_in_progress`（N5 已登记）。
- 通用 CRUD 的定点数（numeric 列）一律输出字符串，跟 D50 一致。`too_many_decimals` 统一改成 `value_error`，带 `ctx.max_places`。
- 5 张履历表的外键改成 RESTRICT。有履历时删除光罩，返回 409 `referenced`，带 `tables[]`。不用删除的话就 scrap。
- 登记 `aggregate_type=reticle`。outbox 按自增 id 排序，`mes_reticle` 不加版本号列。12 个事件的 payload 字段由架构师补进 domain-events.md。
- 补充（删除权限）：光罩删除走通用 CRUD 的 `DELETE /mes/reticle/{id}`，权限是 `mes.reticle:write`，不用 override。有履历时返回 409 `referenced`，`detail` 为 `{code, message, tables[]}`。

## D73 P3-B5 CT/Move 报表契约（2026-10-14，依据前端 p3-ct-move-contract.md + D62/D63/D64）
- 接口：`GET /api/v1/mes/exec/reports/ct-move`，只读，权限 `mes.exec:read`（同 `/reports/wip` 等现有报表）。无权限 403；`operation_id`/`product_id` 不存在或非本租户 404。不需要幂等键，不发事件，不建表、不加迁移（不做预聚合，基于 `mes_lot_history` 实时计算；如需索引另开 0033+ 迁移，先报架构）。
- 参数：`date_from`、`date_to` 必填，`YYYY-MM-DD`，两端都含；可选 `operation_id`、`product_id`（uuid）。`date_from > date_to` 或格式错误返回 422 `value_error`；跨度超过 92 天返回 422 `date_range_too_large`（ctx 带 `max_days=92`）；未知参数按现有查询参数处理（忽略），不报 unknown_field。
- 时区：按站点时区分桶，规则与 D54 导出同一实现；响应带 `timezone`（IANA 名）。响应里的时间点（如有）仍用 UTC Z，`day` 为站点日期字符串。
- 口径（D62/D63）：一次出站算 1 move；`moves` 为批次数（整数），`move_qty` 为出站片数（整数）；拆批、合批、跳站不算；返工出站只计入 `rework_moves`/`rework_move_qty`，不计入前两者。撤销的转换不计入（D60）。
- CT：工序 CT = 上一工序出站（首工序为开批）到本工序出站，按本工序出站日期归日，单位小时，不扣 Hold；子批起点继承母批上次出站时间，合批取各源批最早时间。返回 `ct_avg_hours`、`ct_p50_hours`、`ct_p90_hours`（仅 `by_operation` 带 p50/p90；`trend` 与 `total` 只带 avg）。批次 CT 不在 P3。CT 只统计非返工出站（与产出口径一致）。
- `hold_hours`：按出站批次平均的 Hold 时长（小时），口径同 `ct_avg_hours`；`wip_lots`：`date_to` 当天站点时区日末的在制批数，只在 `by_operation` 给出。
- 数值格式：时长字段为十进制字符串，固定 2 位小数（ROUND_HALF_UP，满足 ≤6 位约定），无数据为 null；计数字段为 JSON 整数，无数据为 0。分位数用线性插值（同 PostgreSQL `percentile_cont`）。
- 形状：`{date_from, date_to, timezone, trend[{day, moves, move_qty, rework_moves, rework_move_qty, ct_avg_hours, hold_hours}], by_operation[{operation_id, operation, operation_name, moves, move_qty, rework_moves, rework_move_qty, ct_avg_hours, ct_p50_hours, ct_p90_hours, hold_hours, wip_lots}], total{moves, move_qty, rework_moves, rework_move_qty, ct_avg_hours, hold_hours}}`。`trend` 列出范围内每一天；`by_operation` 只列有出站或有在制的工序，按工艺路线顺序、再按 operation 编码排序。菜单 key `mes-ct-move-report`、组件 key `mes-page:ct-move-report` 随菜单键导出（D59 补充）一起提交。
- 对前端文档的修正：
  1. `move_qty`、`rework_move_qty` 改为 JSON 整数（片数是整数列 `qty`，不是定点小数，D50/D72 的“定点数输出字符串”不适用）；前端 `normalizeReport` 兼容字符串输入即可。
  2. 时长字段固定 2 位小数字符串（前端示例已是 2 位，此处定为约定）。
  3. `ct_p50_hours`/`ct_p90_hours` 只在 `by_operation` 出现，`trend`/`total` 不带（与前端示例一致，写明避免前端补字段）。
  4. 前端待定 1：p3-tasks.md 的 B5 卡已改为本条口径（单接口、`mes.exec:read`、无批次 CT），`/mes/report/move`、`/mes/report/cycle-time`、`mes.report:read` 作废。
  5. 参数校验失败统一 422 `value_error`（日期格式、`date_from > date_to`），不另起码。
- 待定（工艺专家）：T5-1 “返工出站”的判定：批次在返工路线/返工工步上出站，还是出站带 `rework_units` 也算（以及部分返工时片数怎么拆）？T5-2 `wip_lots` 是否包含 Hold 中的批次。T5-3 Hold 跨工序时 `hold_hours` 归属到 Hold 发生的工序还是出站工序。确认前后端先按：返工路线/工步出站才算返工；wip 含 Hold；Hold 时长归到其所在工序的出站——均为暂定，可改数据口径不改接口。

## D74 P3-B6 人员资质履历契约（2026-10-14，依据前端 p3-operator-qual.md + D62/D64）
- 范围：沿用现有实体 `operator_qual`（表 `mes_operator_qual`，0007）、检查项 `operator_qualified`、`qual_expiry_notice`。新增：资质变更履历、即将到期汇总接口、领域事件。考核记录不做（D62）。权限沿用实体所在模块的 `mes.exec:read` / `mes.exec:write`（以 specs 注册为准，不新增权限名）。
- 迁移 0033（接 D72 的 0032）：新表 `mes_operator_qual_log`：`id`、`tenant_id`、`qual_id`（FK→mes_operator_qual，RESTRICT）、`action`（枚举 `operator_qual_log_action`：granted/renewed/changed/deactivated/reactivated/expired）、`before`/`after`（JSON，变更字段快照）、`reason`（可空，≤300）、`username`、`at`（UTC）；索引 (tenant_id, qual_id, at)；`enable_tenant_rls_sql`（ENABLE+FORCE，策略 `tenant_isolation`）。旧数据不补履历。
- 写入规则：通用 CRUD 新建→granted；改 `expires_on` 且延后→renewed；`is_active` true→false→deactivated，反向→reactivated；其他字段变更→changed；每次写一条，与业务写入同一事务。CRUD 写入不要求 Idempotency-Key（沿用通用 CRUD）。`reason` 可选（请求体顶层 `reason` 字段，CRUD 对该实体放行此字段，不报 unknown_field）。有履历的资质删除返回 409 `referenced`（`tables[]`），改用停用（同 D72）。
- 履历接口：`GET /api/v1/mes/exec/operator-qual/{qual_id}/history`，`mes.exec:read`，403>404；返回 `{rows[{id, action, before, after, reason, username, at}]}`，按 `at` 倒序，支持 `limit`（默认 50，最大 200）/`offset`。
- 即将到期汇总（D64 定稿形状不变）：`GET /api/v1/mes/exec/operator-qual/expiring?days=`，`mes.exec:read`；`days` 为 1–365 整数，不传取设置；非法返回 422 `value_error`（ctx 带 `min=1,max=365`）。只返回 `is_active=true` 且 `days_left` 在 [0, days] 内的行，`days_left` 按站点时区今日计算，排序 `days_left` 升序再 `username`；`expires_on` 为空（永久）的不返回。
- 预警天数单一来源：`operator_qual` 实体元数据 `warn_days`，1–365 整数，缺失/非法按 30。`qual_expiry_notice` 定时提醒也改读这一值（当前代码 `qual.py` 默认 14，改为 30 并读同一来源）。
- 进站检查 `operator_qualified`：不通过 409 `check_blocked`，`overridable=false`（force/override 不能放行，同 D43）；“今日”改用站点时区日期（当前代码用 `ctx.at.date()` 即 UTC 日期，需修）；`expires_on` 当天有效；同时命中“工序+设备类型”和“只按工序”时，`data.expires` 取前者；`data.warn_days` 带上当前设置。
- 事件（进 audit_log，登记 domain-events.md）：`operator_qual.granted`、`operator_qual.renewed`、`operator_qual.changed`、`operator_qual.deactivated`、`operator_qual.expired`。`expired` 由每日定时扫描在到期次日（站点时区）发出，按 (qual_id, expires_on) 去重，同时写履历 action=expired；现有通知事件 `mes.qual_expiring`/`mes.qual_expired` 保留不动。
- 对前端文档的修正：
  1. 读权限写明为 `mes.exec:read`，写为 `mes.exec:write`（文档里的“operator_qual 读权限”即此）。
  2. 汇总接口不返回 `expires_on` 为空的资质，也不返回 `is_active=false` 的资质。
  3. `days` 超出 1–365 后端返回 422 `value_error`，不是静默按 30；只有“设置值”缺失/非法才按 30。
  4. 资质履历接口路径与形状按本条；“考核记录作废”与 B6 卡同步删去考核记录范围。
  5. `pickQual` 只用于界面提示，与后端 `data.expires` 选取规则一致（工序+设备类型优先）。
- 待定（工艺专家/kai mi）：Q6-1 资质过期是否要自动置 `is_active=false`（当前定为不自动改，只发 expired 事件和履历）。Q6-2 停用/延期是否必须填 `reason`（当前可选）。Q6-3 是否需要单独的“资质授予”权限（与 `mes.exec:write` 分开，例如只有班组长/培训员能授予）——当前沿用 `mes.exec:write`。

## D73/D74/D70 补充（工艺专家答复，2026-10-14）
工艺专家的答复标为【推断】，按此定稿；以后改的话只改计算口径或数据，接口不变。
- T5-1（D73 返工口径）：只有在返工路线或返工工步上的出站，才算 rework move，计入 `rework_moves`/`rework_move_qty`。普通工步出站时带 `rework_units`，属于“判返工”，按正常 move 计入 `moves`/`move_qty`，同时把带出的返工片数计入新字段 `rework_qty`（JSON 整数，无数据为 0，只供统计）。`rework_qty` 出现在 `trend[]`、`by_operation[]`、`total` 三处。部分返工靠 M3 拆出子批，片数自然分开，move 里不拆。
- T5-2（D73 在制）：`wip_lots` 含 Hold 中的批次。`by_operation[]` 另加 `on_hold_lots`、`on_hold_qty`（均为 JSON 整数，同一 `date_to` 日末时点，无数据为 0），只在 `by_operation` 给出，`trend`/`total` 不带。
- T5-3（D73 Hold 归属）：`hold_hours` 算到 Hold 所在的工序。批次 Hold 时不能出站，一般不会跨工序；特例（如自动推进）跨工序时，按批次在各工序实际停留的时段把 Hold 时长分摊到各工序。
- Q6-1（D74 过期）：过期不自动停用，`is_active` 不变，只发 `operator_qual.expired` 并写履历。进站检查 `operator_qualified` 直接看 `expires_on`（按站点时区，当天有效，D74），过期即 409 `check_blocked`，`overridable=false`。过期（有效期）和停用（人为处置）是两个独立状态。
- Q6-2（D74 原因必填）：停用（deactivated）和延期（renewed）必须填原因：
  - `reason_id`：引用现有原因码实体 `reason_code`（表 `mes_reason_code`），沿用 `equipment/maint.py` 的 `reason_id` 约定，不另建枚举或配置项。`reason_type` 枚举新增 `operator_qual`（`quality/specs.py` 的 ENUMS；列是 String(40)，不需要迁移）；原因码由租户自己维护，系统不预置。`reason_id` 指向的原因码不是 `operator_qual` 类型或已停用时，返回 422 `value_error`。
  - `comment`：必填，≤300，替代 D74 原来的可选 `reason`（请求体顶层放行 `reason_id`、`comment`、`approved_by`，不报 unknown_field）。
  - 延期另需 `approved_by`（本租户已有的用户名，不存在返回 422 `value_error`）。
  - 缺字段返回 422，code 用 `missing`（同光罩 reason/reason_id）。只有 deactivated/renewed 必填；granted/changed/reactivated 可选，填了也照样记录。
  - 0033 的 `mes_operator_qual_log`：`reason` 列改为 `comment`（≤300，可空），新增 `reason_id`（FK→mes_reason_code，RESTRICT，可空）和 `approved_by`（可空，≤64）。0033 还没提交，直接改，不另开迁移。
  - 事件：`operator_qual.renewed` 和 `operator_qual.deactivated` 的 `reason` 改为 `reason_id`、`reason_code`、`comment`；renewed 另带 `approved_by`（见 domain-events.md）。
- D70 补充（工艺专家意见，已对照 be/p3 代码，只读）：
  1. 粒度：现有 `mes_alarm_code`（0025）本来就是“设备类型 + ALID”，部分唯一索引 `uq_mes_alarm_code_type (tenant, equipment_type_id, alid) WHERE equipment_id IS NULL`，单台覆盖行另有 `uq_mes_alarm_code_eqp`。D70 的“每个报警码一个 `track_in_action`”就是这个粒度，**不需要改表结构，也不需要全局报警码表**。不同机型重号或含义不同，本来就是不同的行。
  2. 迁移：`track_in_action` 还没进 be/p3（B8 未开工）。B8 新开迁移 **0034**（接 0032 D72、0033 D74），在 `mes_alarm_code` 上加 `track_in_action`（枚举 off/warn/block）。类型层的行非空、默认 off（D70 补充）。单台覆盖行可以为空，空表示继承同 ALID 的类型层。旧行回填 off。不新增表。
  3. 生效范围：只算未清除的报警（`mes_alarm_log.cleared_at IS NULL`），同 D70“清除后立即放行”。查找顺序：先找本机的覆盖行，非空就用它；否则用类型层的行；`unregistered=true` 或两层都找不到时，不参与判断。
  4. 多腔体：`mes_alarm_log` 已有 `sub_unit_id`（0025，可空，由上报决定）。但进站/批次目前不记录用哪个子单元（execution 代码里没有 sub_unit）。所以 P3 先按整机拦截：报警带不带 `sub_unit_id`，都拦这台设备。`ctx.alarms[]` 带上 `sub_unit_id`，便于提示。“只拦报警所在腔体”列为待定，要等进站能带子单元（或有路线到腔体的指派数据）后再做，不在 P3-B8 里编造。
  5. 种子数据：报警码按厂商和机型定义，系统不预置具体 ALID。下面按类别给出配置模板，由工艺/设备工程师按机型逐码填写：
     - block：真空或腔体压力超限、漏率异常；温控超限（腔体、卡盘、炉管、药液）；射频或等离子体电源故障；MFC 故障或气源中断；ESC 吸附失败；机械手碰撞、晶圆滑片、碎片、定位失败；安全类（气体或液体泄漏、排风异常、门联锁、EMO）；光刻对准或焦距超限、光源能量异常；CMP 研磨液中断、终点检测失效。
     - warn：耗材即将到寿命、药液或气体余量偏低、过滤器压差偏高、传感器轻微漂移、通信瞬断或超时后已恢复、载具读码失败可重试。
     - off：信息类提示、维护模式下的门开、操作员提示消息。
     - 例外：量测机台大多配 warn，只有传片碰撞和安全类配 block；后道分选机卡料配 warn，测试机接触或校准失败配 block；多腔体机台见第 4 点。
     这份模板写进 B8 的说明文档，不做迁移种子。
- 仍待定：多腔体只拦子单元（见上）；Q6-3 单独的资质授予权限（等 kai mi 定，暂时沿用 `mes.exec:write`）；`approved_by` 能否等于操作人本人（暂时允许）。
- 补充（Q6-3，kai mi 2026-10-14 定）：资质授予不单独设权限，按正常 RBAC 管控，沿用 `mes.exec:write`。
- 补充（D70 来源层）：报警码配置的读接口在 `effective_track_in_action` 之外再加只读字段 `effective_track_in_action_source`，取值 `equipment` 或 `equipment_type`。EAP 报警上报的腔体字段为 `sub_unit_id`，可选，必须属于本台设备。
- 补充（只读字段）：写接口（PATCH/POST）带 `effective_track_in_action`、`effective_track_in_action_source` 等只读字段时，按写入 schema 不认识的字段处理，返回 422 `unknown_field`，不静默忽略（同 `status_code`）。
- 补充（D74 approved_by）：延期的 `approved_by` 不能是操作人本人，否则返回 422 `value_error`，`ctx.reason=self_approval`。
- 补充（D70 缺类型行）：禁止“单台设备行存在而对应 (设备类型, 报警码) 类型行不存在”。新建单台行时类型行缺失返回 422 `value_error`，`ctx.reason=type_row_missing`；删除仍被单台行引用的类型行返回 409 `referenced`。设备未挂设备类型时不能建单台行，返回 422 `value_error`，`ctx.reason=equipment_type_missing`。0034 迁移对已有的、缺类型行的单台行自动补一条类型行，`track_in_action=off`，不让迁移失败；迁移日志打印补了几行。
- D75（业务日期统一，2026-10-15）：凡是按"今天"判断的业务规则（资质、设备认证、工具寿命、到期提醒等），一律用站点时区的日期，和 D54 共用 `excel.tenant_tz`，禁止用 `at.date()`（UTC）或 `date.today()`（服务器本机日期）。前端同理，不用 `toISOString().slice(0,10)`。先修 be/p2，复测通过后 P2 才能推送；同一修复合进 be/p3。
- D75 补充：会话/租户信息返回 `site_tz`（取 `tenant_tz()`），前端全局只读这一个，跟 B6 一起交；在那之前前端从厂区列表取，取不到用 Asia/Taipei。`mes_reticle_applicability` 是适用关系表，按 D72 保留 CASCADE。
- D76（定点输出范围，2026-10-15）：D50 的定点输出成字符串的规则覆盖所有接口，包括专用接口，不只是通用 CRUD 和 BOM：带 scale 的 numeric 列一律输出字符串，整数列一律输出 JSON 整数。专用接口（载具、进站上下文 ctx 等）按这条规则排查，在 be/p3 单独出一个提交，提交前先在群里列出要改的字段。服务端换算和计算定点值时一律用 Decimal，禁止经过 float（`uom.py` 的 `float(v)` 改成 `Decimal(str(v))`）。`scrap_rate` 的 scale 统一为 4。
- D75 补充（2026-10-15）：D75 覆盖所有按「今天/当天」计算的业务逻辑，不只限有效期检查。`planning/board.py:51` 交期风险、`dispatch.py:157`、`router.py:296` 当天统计改用 `site_today()`，并按站点时区算当天边界，放 be/p3，不影响 P2 推送。代码中禁止新增 `date.today()`、`datetime.now()` 不带时区和 `.date()` 取 UTC 日期的写法，测试评审加检查。`site_tz` 位置定为 `/tenants/me` 的 `tenant.site_tz`。通用 CRUD datetime 筛选边界由前端按站点时区算，发送时带偏移。

## D77 — 范围筛选边界约定（2026-10-15）
- datetime 范围一律半开区间：`_from` 用 `>=`，`_to` 用 `<`。前端发站点日期次日 0 点（带当天实际偏移）作为结束值。
- date 类型字段（站点日期）按日历日闭区间 `[from, to]`，后端内部换成 `< to+1 天`。
- 通用 CRUD 的 datetime `_to` 在 be/p3 从 `<=` 改为 `<`，与前端 `rangeParam` 同一版本上线，不单独发布。坐标图 `imported_to` 已符合。
- 新接口必须遵守；接口说明写明边界。测试对每个范围筛选加「等于边界值」用例。

## D78 — 打标记录（P3-B2，回应 P3-E2 预审 Q1–Q7）（2026-10-15）
- Q1 每次打印（首打和重打）追加一行子记录 `mes_marking_print`（seq 从 1 起），各自带 source/external_event_id，去重用部分唯一索引 `(tenant_id, source, external_event_id) WHERE external_event_id IS NOT NULL`。重打（seq>1）必填 `reason_id`+`comment`（≤300），reason_type=`marking_reprint`；缺了 422 `missing`。主记录的 reprint_count 只读、派生。
- Q2 本期不加 sub_unit_id。
- Q3 EAP 回报的 trace_code 与系统发号不一致：409 `trace_code_mismatch`，ctx 带 expected/actual，写 audit_log。OCR 读回与计划不一致：检验记 fail，存 expected_code/read_code，发 `label_marking_mismatch` 事件。
- Q4 检验结果独立成 `mes_marking_inspection`，带自己的 source/external_event_id，去重规则同 Q1。
- Q5 检验不合格且未处理时出站：409 `check_blocked`，ctx.check=`marking_inspection`，overridable=false。
- Q6 手工打标、重打、检验接口必须带 Idempotency-Key，缺了 422 `missing`（loc=header）。按 D57 处理。
- Q7 trace_code 长度和字符集待工艺专家确认；暂按 ≤32、`[A-Z0-9-]` 实现，并做成可配置。
- 已报废对象做打印、检验或上报：409 `invalid_transition`，不计数、不发事件。
- p3-tasks §0 的 `too_many_decimals` 改为 `value_error`（D72）。
- D78 补充：seq 由后端分配，机台只带事件号；加唯一约束 `(marking_id, seq)`；分配时对主记录 `SELECT ... FOR UPDATE`。去重命中（duplicate=true 或 Idempotency-Key 重放）先于分配，不占 seq。
- D78 补充二：
  1. trace_code 超长或含非法字符时返回 422 `value_error`，ctx.reason 取 `max_length` 或 `pattern`。手工打印和 EAP 上报两处入口都要校验。
  2. OCR 不一致事件改名为 `lot.marking_mismatched`。`label_marking_mismatch` 只保留作 B3 出货标签比对的 409 错误码。
  3. 「已报废对象」包括两种：批次已报废，或者打标记录已作废。作废接口为 `POST /mes/marking/{id}/void`，必填 reason_id 和 comment，reason_type 用 `marking_void`，权限跟 B2 的写权限相同。作废后不可恢复。
  4. 检验行挂在 print_id 上。check_blocked 只看最新一次打印（seq 最大）的最新一次检验：结果是 pass 就放行；还没检验或结果是 fail，就返回 409。重打本身不算处理，旧打印的 fail 不再拦截。主记录加只读字段 `latest_inspection_status`，取值 pending、pass、fail。检验履历带 print_id 和 seq。
  5. 缺 Idempotency-Key 时，loc 为 `["header","Idempotency-Key"]`。
  6. 手工接口重放按 D57 处理：返回原状态码和原记录，不带 duplicate 字段。duplicate=true 只用于 EAP 事件上报。
- D78 补充三：
  1. 事件 `lot.marked`、`lot.marking_inspected`、`lot.marking_voided` 已登记到 domain-events.md，payload 见该文件。
  2. void 必须带 Idempotency-Key，规则跟其他手工接口一样。
  3. void 用新权限 `mes.marking:void`，按正常 RBAC 分配，不并入 `mes.marking:exec`。
  4. trace_code 同时违反多条规则时，422 的 detail 逐条列出。max_length 那条带 ctx.max_length，pattern 那条带 ctx.pattern，取值都是当前生效的配置。
  5. 先做请求体校验：返回 422 就不进业务逻辑，不返回 409、不写 audit_log、不发事件。
  6. 新增 `GET /mes/marking/config`，权限 `mes.marking:exec`，返回 trace_code_max_length 和 trace_code_pattern，随 B2 一起交付。
- D78 补充四：
  1. `lot.marked` 的 payload 固定带 reason_id 键，seq=1 时值为 null。comment 不放进 payload，需要时按 print_id 查询。
  2. `trace_code_pattern` 返回带 `^…$` 锚点的完整正则，长度只由 trace_code_max_length 控制。正则只允许用字符类、`^`、`$`、`+`，不用 `\d`、`\w`，也不用 flag；配置写入时后端按这个规则校验。
  3. 空串或纯空白返回 422 `missing`，只报这一条，不再叠加 pattern。
  4. 前端不修改用户输入，不去空格、不转大小写，提交原值，只做提示。后端也不做规范化。
- D78 补充五：「纯空白」用正则 `^[ \t\r\n\u3000]*$` 判断，三端都用这个正则，不用 strip()/trim()。命中就只报 `missing`；其他值一律不做规范化，直接全串匹配（后端用 re.fullmatch）。U+FEFF、`\x1f` 等不算空白，报 `pattern`。

## D79 — 打标模板与作业接口细节（P3-B1~B3，回应 P3-F4）（2026-10-15）
1. 模板 lines 是字符串数组，占位符写成 `{name}`，只允许白名单里的名字（trace_code、date_code、lot_id、product_code、customer_code），否则 422 value_error，ctx.reason=unknown_placeholder。新版本用 `POST /mes/marking-template/{id}/versions`，复制最新版本为草稿，版本号由后端递增。模板返回 created_by，以及只读的 product_name、customer_name。
2. 错误码：起草人审批自己的模板返回 422 value_error，ctx.reason=self_approval（同 D74）；修改已批准版本返回 409 `template_readonly`；已有草稿时再建版本返回 409 `draft_exists`；批次已有未作废主记录时再首打返回 409 `already_marked`。
3. `POST /mes/marking` 创建主记录，所有打印（含首打）走 `POST /mes/marking/{id}/prints`，seq 由后端分配。EAP 上报落到同一套逻辑。
4. 检验填了 pass 但读回码不一致时，强制记为 fail，不返回 422。响应带 result=fail、expected_code、read_code 和 result_overridden=true。
5. 作废后允许同一批次重新首打：新建主记录，seq 从 1 开始。同一批次最多一条未作废主记录，用部分唯一索引保证，并发时另一条返回 409 already_marked。追溯默认不含已作废记录，传 include_voided=true 才包含。
6. 筛选参数为 marked_at_from 和 marked_at_to，按 D77 半开区间。打标表没有 qty。kind=trace_code 的追溯结果返回 {marking_id, lot_id, trace_code, voided, prints[{print_id, seq, marked_at, latest_inspection_result}]}。
7. 菜单 key mes-marking 和 mes-marking-template 在 B2 登记，并导出到 menu_keys.json。权限：`mes.marking:read` 同时覆盖模板和作业的读；模板编辑用 `mes.marking_template:write`，审批用 `mes.marking_template:approve`；打印和检验用 `mes.marking:exec`，作废用 `mes.marking:void`。
- D79 补充：
  1. trace_code 追溯沿用 `GET /mes/exec/trace?kind=trace_code&code=`，权限 `mes.exec:read`，不新增 mes.trace:read，B3 卡已改。
  2. EAP 上报按「批次当前未作废的主记录」定位，不自动建；找不到（含只有已作废记录）返回 409 `no_active_marking`，不写打印、不发事件。
  3. `result_overridden` 始终返回，未改写时为 false。
  4. 作废后旧主记录保留原 latest_inspection_status；check_blocked 只看未作废主记录。
  5. 产品绑定了已批准打标模板即视为要求打标。要求打标但无未作废主记录、或最新打印未检验/为 fail，出站返回 409 `check_blocked`，ctx.check=`marking_inspection`，overridable=false。未绑定模板不检查。
  6. check_blocked（marking_inspection）的 ctx 加 reason，取值 `not_marked`、`pending`、`fail`；有主记录时同时带 marking_id。
- D79 补充二：
  1. 同一次打印可以检验多次，以最新一次为准。批次离开打标工步后不能再检验，返回 409 `invalid_transition`。
  2. trace_code 长度按 Unicode 码点算：后端用 len()，前端用 [...s].length。
  3. 读回码不校验格式，不合规也照样记录，按不一致强制记 fail，原值存进 read_code。空值返回 422 missing；超过 128 个码点返回 422 value_error，ctx.reason=max_length。
  4. 配置正则只允许正向字符类，类里只能有大写字母、数字和区间，`-` 只能放在类的最后。不允许 `[^…]`，也不允许任何反斜杠转义。写配置时按这个白名单校验。
  5. 重打不要求上一次检验为 fail，但必须填原因（D78）。
  6. 主记录 marked_at 取首打（seq=1）时间、不再变；只读 last_printed_at 取最近一次打印时间；marked_at_from/_to 按 marked_at 筛选。

## D79 补充三（2026-10-15 02:10，定稿 PEND-MK-07/08）
- read_code 缺字段、null、""、纯空白（按 D78 补充五 `^[ \t\r\n\u3000]*$` fullmatch）一律 422 `missing`，loc `["body","read_code"]`，不落库、不强制 fail。
- 非字符串（数字/布尔/数组/对象）→ 422 `string_type`。
- 非空白字符串：不做格式校验，不 trim；>128 码点 → 422 `max_length`；与 expected_code 不一致 → 强制 fail + result_overridden=true。
- U+FEFF、\x1f 等不算空白，按普通字符串处理（不一致即 fail）。

## D80 光罩上报去重与幂等（2026-10-15 02:12，E2 光罩侧 G1–G6）
- G1：下机单独记一行事件（mes_reticle_mount_event 或同表 event_type=unmount 行，以后端现结构为准），沿用 (tenant_id, source, external_event_id) 部分唯一索引；上机行只回填 unmounted_at，不再写事件号。
- G2/G3：手工写接口 Idempotency-Key 一律必填（usage/incident/inspection/mount/unmount），缺失 422 missing loc ["header","Idempotency-Key"]，重放按 D57。后端列受影响接口清单；前端、模拟器、P1/P2 冒烟脚本同版本上线。
- G5：mounted/unmounted/life_reached 事件 payload 补 source、external_event_id（手工为 null）。
- G6：source 加 CHECK (manual/eap/simulator/system)；迁移先统计非法值，NULL→manual、其他→system，记日志行数（同 0034）。
- G4 不在 P3；G7 待 H-1 合入后复测。

## D80 补充一（2026-10-15 02:14）
- /mes/reticle 下 hold、release、restore、life-reset、scrap 同样 Idempotency-Key 必填，D80 共 10 个写接口，无例外。
- 同 key 不同请求体按 D57 返回 422 idempotency_key_reused。

## D79 补充四（2026-10-15 02:18，长度/格式错误字段）
- 超长：type=value_error，ctx={reason:"max_length", max_length:N}；trace_code 的 N 取 config，read_code 的 N=128。
- 格式：type=value_error，ctx={reason:"pattern", pattern:"<config 原样正则>"}（仅 trace_code）。
- 补充三中“422 max_length”为简写，以此为准。
- at_marking_step：只读布尔，当前工步为该记录打标工步且未作废时为 true；后端 409 invalid_transition 兜底。

## D79 补充五（2026-10-15 02:19，N-X1）
- 本期 trace_code_pattern 只允许单个正向字符类 `^[...]+$`（规则同补充二），不支持多类串联和 {m,n} 等量词；前缀/分段需求留到后续阶段。
- 后端保存 config 时按同一白名单校验，不合规返回 422 value_error ctx.reason=pattern_unsupported，所以库里不会出现其他写法；前端“不合规不预校验”的分支仅作兜底。
- 补充五续：config 表随 B2 迁移新建，B2 之前无存量。迁移若遇已有行（如手工预置）按白名单检查，不合规重置为默认值并记日志行数；运行时不再做兼容分支。

## D80 补充二（2026-10-15 02:30）
- 范围扩为 14 个：另加 clean-start、clean-complete、repair-complete、inspect-start（_flow 路由），同样必填。/mes/eqp 物料批上机/下机不在范围。
- idempotency_key_reused 维持 D57 对象格式 {code, message}，本期不改（避免影响已回归的 P1/P2）；统一为 err_422 数组格式记入待办，P1/P2 推送后单独一个提交处理。D80 补充一中“422 idempotency_key_reused”指 HTTP 422 + 对象格式。
- 补前端缺口：光罩页加「上机」「登记异常」对话框，走 /mes/reticle/{rid}/mount、/incident，与 D80 同版本上线。

## D77 补充一（2026-10-15 02:32，QA P3-4/P3-5）
- datetime 筛选 _from/_to 必须带偏移（Z 或 ±hh:mm），只传日期或无偏移 → 422 timezone_required，loc ["query","<字段>"]；date 字段不受影响，仍只传日期、闭区间。
- from > to → 422 value_error ctx.reason=range_inverted（date、datetime 都适用）。from == to：datetime 半开区间返回 200 空结果；date 闭区间返回当天数据。
- 后端、前端、模拟器、P1/P2 冒烟脚本同批发布（同 D77-04）。

## D79 补充六（PEND-MK-08）
- 未首打的主记录：marked_at、last_printed_at 字段始终输出，值为 null；latest_inspection_status 为 null（无 print）。筛选 marked_at_from/_to 不命中 null 行。

## D73 补充一（2026-10-15 02:37，CT/Move 口径，B5 2c19bb3）
1. CT 只取主路线（非返工）出站；返工后回原工步，CT 从回到该工步的时刻起算，不含返工耗时。
2. 跳站/分支不计 move、不重置 CT 起点。
3. 子批 Hold 只计自身 lot_hold（拆批时生效的复制；母批已解除的不计）。
4. rework_qty 按写返工履历的时间与工序归日；返工路线上的出站不计。
5. 在制按 date_to 站点日末，从履历还原工步。
6. 工序排序取任一主路线上最小 seq。
7. 缺日期 422 missing；非法 uuid 422 value_error。
8. 追溯不到开批的批次计 move，不进 CT/Hold 样本。
- 跨度：含两端的天数 ≤ 92（即 to − from ≤ 91），超出 422 date_range_too_large ctx {max_days:92}。
- 分桶：按出站时间的站点日归属。无数据的天：计数类为 0，时长类为 null。
- 1–4 抄送工艺专家，如有意见再出补充。

## D81 写接口校验顺序（2026-10-15 02:42，通用）
1) 认证/权限 401/403 → 2) Idempotency-Key 缺失 422 missing → 3) body/query 422 → 4) 幂等重放（同 key 同体返回原响应；同 key 异体 422 idempotency_key_reused）→ 5) 资源 404 → 6) 状态/业务 409。
- 适用 D57/D78/D80 所有写接口；与“403→404→409”“422 先于业务”一致。
- 补记：trace_code_pattern 类里至少一个大写字母/数字/区间，`^[-]+$` → 422 pattern_unsupported，loc ["body","trace_code_pattern"]；检验请求缺 read_code 字段 → 422 missing。
- D81 范围：本期只约束 P3 新接口和 D80 的 14 个接口；P1/P2 已回归接口不动，QA 盘点差异，P1/P2 推送后与 reused 格式统一合并为一个单独提交。

## D82（2026-10-15 02:49，P1/P2 收尾范围 + 补录时间）
- P1/P2 收尾提交（推送后）：reused 改数组格式 + D81 顺序（权限前置、404/422 顺序）+ 写接口必填 key。豁免：只读性质的预览/校验 POST，和 /mes/eap/events（靠 external_event_id 去重）。
- 状态冲突 422→409 属对外契约变更，不进该提交，另立待办单议，届时先盘点前端按状态码分支的地方。
- 出站拦截：主记录已建未首打 → ctx.reason=not_marked 且带 marking_id（确认后端方案）。
- 补录时间 mounted_at/occurred_at：晚于服务器当前时间 5 分钟以上 → 422 value_error ctx.reason=future_time；早于该光罩最近一次下机/事件时间 → 409 time_out_of_order（依赖库内状态，按 D81 归业务校验）。
- D82 续：future_time 判定为 > 5 分钟（恰好 5:00 放行）；unmounted_at < 对应 mounted_at → 409 time_out_of_order，相等合法。
- D82 补正：第 4 点同样适用 unmounted_at；三个时间字段不带时区 → 422 timezone_required（body 校验阶段）。

## D73 补充二（2026-10-15 02:53，B5 复测 P3-1/P3-2）
- 带 rework=true 离开主路线的那次出站：计 move，不进 CT 样本（该工步 CT 以返工回来后的那次出站为准，见补充一第 1 点）。
- Hold 期间部分报废：暂按现状允许，_QTY 计入 scrap；是否须走 MRB/限权限待工艺专家确认，如改另出提交。
- D82 续二（03:19）：时间先后基准 = 状态履历与历次下机中最晚者（usage/检查不计）——适用 mount/unmount。incident 额外把最近一次 usage 计入基准：occurred_at 早于最近 usage → 409 time_out_of_order（避免 Hold 后仍有使用记录）。incident 顺带下机用 occurred_at（无则当前时间）；occurred_at < 当前 mounted_at → 整体 409，不入库不下机。

### D77 补充二（03:30）
- 采纳方案 A：output/oee 执行报表 from>to 改为 422 value_error，ctx.reason=range_inverted，废止 D65 补充 3 的 date_range_invalid（前端旧码文案在后端提交后删）。
- 通用 date 筛选改为严格 YYYY-MM-DD，带时间返回 422 value_error（ctx.reason=pattern）；与 A 同一小提交，排在 D80 之后。
- 旧履历返工 2 秒窗口识别本期不动，记为已知限制。

### D82 补充一（03:48）
- 光罩未挂载时补录 unmount：先判状态，返回 409 invalid_transition，不再判 time_out_of_order。
- 上机页签每次上机只显示一行，下机时间取自上机行；event_type=unmount 的行不在该页签单独显示。
- 三语文案以 fsft-fe 为准，后端仓库不改 frontend/src/i18n。

### D82 补充二（04:16）
- inspection 的 inspected_at 也受时间顺序约束：早于最近一次状态变化（含 inspect-start）返回 409 time_out_of_order，是预期行为。
- `/mes/eap/events` 先查重复再校验 payload，与 D81 相反；本期不改（D81 只覆盖 P3 新接口和 D80 的 14 个），留到下一阶段与 EAP 光罩上报草案一起处理。
- 在共用环境（8011/8012/8013）里不跑 `setup_db_roles.py`，因为它会改共用 app_user 的密码；迁移需要授权时写进迁移本身。

### D79 补充七（04:19）
- D81 细化：要查到记录才能判断的 422（重打 seq>1 时 reason_id/comment 必填、self_approval）排在 404 之后、409 之前。
- 自己审批自己写的模板：先 422 self_approval，再 409 invalid_transition。
- comment 超长：value_error，ctx={reason:"max_length", max_length:N}，长度按码点算。reused 本期为对象格式。
- 出站 409 check_blocked：顶层 code+ctx，results[] 每项含 check_type、result、ctx（沿用现有字段名，04:28 更正）；打标项 ctx 带 marking_id 和 trace_code（未首打时 trace_code 为 null）。
- 模板的创建、编辑、新版本、审批都是写接口，必须带 Idempotency-Key。
- 登录 500 的根因是 app_it_eap 恢复时用了缺授权的备份，与 0035 无关；迁移里不另补授权。
- D79 补充七附注（04:28）：模板创建和新版本返回 201，编辑和审批返回 200；comment 上限 300。
- D79 补充七附注二（04:31）：模板预览和校验接口为 `POST /mes/marking-template/preview` 和 `/validate`，路径不带 {id}。请求体二选一传 template_id 或 lines，两个都传或都不传返回 422 value_error。预览返回 {template_id, lines}，校验返回 {valid, unknown_placeholders}。只读，不要 key，返回 200；template_id 不存在返回 404。
- D79 补充七附注三（04:34）：预览和校验的二选一 422 为 value_error，loc ["body","template_id"]，ctx {reason:"exactly_one_of", fields:["template_id","lines"]}；两个都传和都不传返回相同内容，排在 404 之前。

### D83 数据库授权（04:43）
- 新增迁移 0036：给运行时角色授予现有全部表和序列的权限，并设 ALTER DEFAULT PRIVILEGES，之后新建的表自动带授权。可重复执行；角色名从配置读取；迁移里不建角色、不改密码。0036 排在 B6 之前。
- conftest 不再调用 setup_db_roles.py。测试库的授权靠 alembic upgrade head（含 0036）完成。
- setup_db_roles.py 只用于首次建角色，由人工在明确的环境里执行；共享环境禁止运行（见 D82 补充二）。
- 验收：全新库和现有库都只跑 alembic upgrade head，app_user 就能登录和读写。

### D82 补充三（04:48）
- 409 的 detail 保持 {code, message}，可以在顶层附加上下文字段，比如 time_out_of_order 带的 latest_event_at（UTC，以 Z 结尾）。409 不使用 ctx。这一阶段不改，前端和测试按顶层取值。

### D77 补充三（04:49）
- 报表的 date_from/date_to 也只接受严格的 YYYY-MM-DD。带时间的值返回 422 value_error，ctx.reason=pattern。校验顺序：先查格式，再查 range_inverted。属于 P3，放进后端下一个提交（0036 之后、B6 之前都可以）。

### D82 补充四（04:58）
- check_blocked 是 D82 补充三的例外。它装的是多条检查结果，继续用 results[]，每项包含 check_type、result、ctx，和 D79 补充七一致。顶层附加字段只用在单一原因的 409 上，比如 time_out_of_order。
- fe-it-ro 跟 fe-it 一样只用于联调，P1 之后一起停用；凭据只放在文件里，不进聊天。

### D83 补充一（05:13）
- 0036 的 ALTER DEFAULT PRIVILEGES 写成 FOR ROLE <迁移角色>（采纳 QA 建议）。
- scripts/prestart.sh 去掉对 setup_db_roles.py 的调用，部署只跑 alembic upgrade head。角色只在首次建库时人工建一次。随下一个后端提交修改，部署仍需 kai mi 批准。
- TODO：members/new 在角色不存在时先建了用户再返回 400，操作不是原子的。归为 P3，排在 B8 之后修。

### D84 B8 报警等级拦进站契约（05:13）
- Q1：进站被拦时返回 409 check_blocked，results[] 列出所有没通过的检查项，result 只取 block 或 warn。只要有一项是 block 就拦。
- Q7：只有 warn、进站成功时，warnings[] 每项改成 {check_type, result:"warn", ctx}，跟 results[] 同一个形状。
- Q2：报警时间超前返回 422 value_error，ctx.reason=future_time，允许超前 5:00，超过 5:01 拒绝（同 D82）。time_in_future 不再使用。
- Q3：reused 本期用对象格式（同 D80 补充二），不开例外。
- Q4：改配置按 /mes/alarm_code/{rid} 定位；找不到返回 404，code=not_found。
- Q5：409 referenced 的顶层附加 ref_type 和 ref_count（D82 补充三）。
- Q6：新建、修改、删除报警码都必须带 key。
- Q8：按 a72b85b 的实现确认：返回 value_error，reason=pattern 或 timezone_required。

### D84 补充一（05:15）
- 更正 Q7：本期 B8 的 warn 项也用 {code, ctx}，warnings[] 里只保留一种结构。等 P1/P2 推送后，统一改成 {check_type, result, ctx}，和 reused 改数组放在同一批提交，前后端一起上线。

### D84 补充二（05:20）
- 更正 Q8 的写法：不带时区时返回 type=timezone_required，没有 ctx.reason（D77 补充一）；只有无法解析的值才返回 type=value_error 加 ctx.reason=pattern。

### D85 B6 细节与等值筛选（05:32）
- D77 也管等值筛选。datetime 字段的等值筛选和 _from/_to 走同一套校验：只给日期或不带时区返回 timezone_required，无法解析返回 value_error 加 reason=pattern。随 FOR ROLE 小提交修。
- B6 进站检查项名用现有的 operator_qualified（更正 05:09 验收要点里的 operator_qual）。
- operator_qual 的写接口必须带 key（以 B6 验收要点为准，D74 原文作废）。
- 停用和延期的判断方式：PATCH 里 is_active=false 算停用，带 expires_on 算延期。不另开动作接口。恢复只写履历、不发事件。
- 自批两种都拦，都返回 422 value_error：
  - approved_by 等于发请求的用户：ctx.reason=self_approval，属于请求体校验，排在 404 之前。
  - approved_by 等于被授予资质的人：ctx.reason=holder_approval，要先查到记录，排在 404 之后、409 之前。

### D85 补充一（05:39，记录后端确认）
- 资质 DELETE 也必须带 key（D81）。
- 只要请求带了 expires_on 就算延期，必须有 reason_id、comment、approved_by。新到期日比原来晚记 renewed，早则记 changed，并发对应事件。
- 本身以 _from/_to 结尾的字段（比如 effective_from/effective_to）做等值筛选时，不能当成区间后缀剥掉。

### D85 补充二（05:44）
- 有意设计：资质只能停用，不能删除，履历要留作审计。DELETE 接口保留，执行完整的 D81 校验后总是返回 409 referenced，顶层带 ref_type=operator_qual_log 和 ref_count。前端去掉删除按钮，测试计划按「删除总是返回 409」写。
- 履历 rows[] 带 comment、reason_id、approved_by，跟表的列一一对应。
- check_blocked 里 operator_qualified 那一项的 ctx 带 qual_id 和 expires_on，expires_on 用 YYYY-MM-DD 格式。
- 授予不要求 reason_id、comment、approved_by。允许新建 expires_on 已经过期的资质，可以直接用作测试种子数据。
- 同一个 PATCH 同时带 is_active=false 和 expires_on 时，返回 422 value_error，loc ["body","expires_on"]，ctx.reason=conflicting_fields，属于请求体校验阶段。
- 路径和 reason 类别以 B6 提交为准（reason_type=operator_qual，D74）。

### D83 补充二（05:46）
- prestart.sh 保留 python -m app.initial_data，前提有三个：可以重复执行；已有的用户和数据一律不覆盖，尤其不重置已有账号的密码；不执行任何 ALTER ROLE 或 GRANT。后端在第二个提交里核对一遍，不满足就改到满足为止。
- docker-compose.prod.yml 去掉对 setup_db_roles 的调用（QA 提的 P2-1）。

### D86 幂等缓存范围（05:50）
- 幂等缓存只保存 2xx 的成功响应。4xx（包括 409、422、404）不保存，key 也不算占用；同一个 key 重发时重新跑全部校验。
- 所以资质删除用同 key 同体或同 key 换目标重发，都还是返回 409 referenced（或 404），不会返回 reused。reused 只在这个 key 已经存过成功响应、而请求体或目标变了的时候出现。
- 如果后端现有实现跟这里不一样，在 B6 提交说明里写明，由架构师复议。

### D86 补充一（05:51）
- 409 referenced 最后统一成顶层 ref_type/ref_count。光罩删除这一期继续用 D72 的 tables[]，等 P1/P2 推送后，放进格式统一的那批提交（跟 reused 改数组、warnings[] 改新格式一起），前端、模拟器、测试一起改。
- 8013 是设备集成自己的环境，管理员账号由设备集成从自己环境的 .env 或初始化配置里取。真找不到，就在自己的 app_it_eap 上重跑 initial_data 或重新初始化建管理员。凭据只放文件，权限 600。这件事不上报 kai mi（kai mi 已明确：凭据问题不找他）。

### D86 补充二（06:08）
- 回放的标记：回放成功响应时加响应头 Idempotent-Replayed: true，响应体不动；第一次执行不带这个头。
- ref_type 取被引用的那张表在业务上的名字：报警码用 alarm_record，资质用 operator_qual_log（D85 补充二）。
- 如果后端现有实现跟这里不一样，在 B6/B8 提交说明里写出来，由架构师复议。

### D85 补充三（06:14）
- 更正 D85 补充二：conflicting_fields 的 loc 是 ["body","is_active"]，ctx 是 {reason:"conflicting_fields", fields:["is_active","expires_on"]}，跟 exactly_one_of 的格式一致，排在 404 前面。

### D85 补充四（2026-10-15 06:26）
- 所有 datetime 列（无论是否在筛选里声明）的等值筛选：先按 D77 校验（缺时区 timezone_required；无法解析 value_error reason=pattern），通过后换算为 UTC，按完整精度（微秒）精确匹配，不截断到秒。
- 日常时间查询用 `_from`/`_to` 半开区间；等值筛选只用于精确定位单条记录。

### D87（2026-10-15 06:31）光罩读接口与检验流程
- 光罩 GET 详情和列表补 `life_state`（与写操作 brief 同算法，后端为准），B6 之后的小提交；补前前端自算（warn_ratio 空按 0.9），补后改用后端值。不新增 `inspection_pending`，用 status + inspection_required 判断。
- 检验必须先开始检验（available→inspecting）再提交结果；available 直接提交检验结果返回 409 invalid_transition，属有意设计。
- warn_ratio 为 Numeric(18,4)，最多 4 位小数。

### D87 补充一（2026-10-15 06:36）
- 光罩主数据通用 CRUD（新建/编辑/删除）加入 KEYED_ENTITIES，缺 key 返回 422 missing，口径同 D84 Q6。后端与 D87 life_state 同一小提交；前端立即带 key（后端未强制前多带无害）。

### D87 补充二（2026-10-15 06:51）
- 前端 KEYED_ENTITIES 立即加入 `alarm_code`（路径 /mes/alarm_code/{rid}），新建/编辑/删除带 key；B8 落地前多带无害。
- "待检验"排除已报废光罩（报废为终态），以 status 为准。
- 同 key 不同请求体：422，ctx.reason=reused。

### D87 补充三（2026-10-15 07:03）
- 更正 D87 补充二第三条：本期同 key 不同请求体返回 422，detail 为对象 `{code:"idempotency_key_reused", message}`，无 ctx；数组项 + ctx.reason=reused 仅在格式统一批次后使用（同 D84 Q3）。

### D88（2026-10-15 07:16）B6 落地确认
1. 资质迁移编号为 0037（D74 中 0033 作废）。
2. 通用 CRUD 必须带 key 的实体：reticle、alarm_code、operator_qual；其余按 D80。D74 与前端文档同步更新。
3. Excel 导入资质只允许新建授予；任何会改动已有资质 is_active/expires_on 的行整行拒绝（value_error, reason=use_api），停用/延期一律走 PATCH。后端单独小提交，排在 B1 前。
4. 缩短有效期同样需要 approved_by（同 D85 补充一，履历记 changed）。

### D88 补充一（2026-10-15 07:26）
- 资质 history rows[].at 统一 UTC 带 Z（随 D88-3 小提交修）。
- 通用 404 detail 对象化归入格式统一批次；本期只断言状态码。
- opq-01 中需第二批准人的 10 条及只读账号 1 条由 QA 在 8012 覆盖；8013 不补账号，保留跳过并注明"由 QA 覆盖"，不再等 kai mi。

### D88 补充二（2026-10-15 07:36）
- 已停用资质再停用：无变化，200，不写履历、不发事件（同通用 PATCH 无变化）。
- approved_by 超 64 字符报 user_not_found，无单独 max_length。
- history 404 对象 vs 通用 404 字符串的差异归入格式统一批次。

### D89（2026-10-15 07:48）B1/B2 打标接口细节
1. 模板请求体：code(≤64, 租户内唯一)、name(≤128)、description(可选 ≤300)、lines[]{seq, content}。
2. unknown_placeholder：422 value_error，loc ["body","lines",i,"content"]，ctx {reason:"unknown_placeholder", placeholder}，每个未知占位符一条。
3. version 整数从 1 起；status ∈ draft|pending|approved|retired。
4. 草稿可编辑；pending/approved/retired 编辑返回 409 template_readonly；已有草稿再建版本返回 409 draft_exists（D79-2）。
5. 重打 reason_id 与 comment 都缺：分两条 missing。
6. 打标 check_blocked 项：check_type="marking"，result="block"，ctx {reason ∈ not_marked|pending|fail, mark_id(not_marked 时为 null)}。

### D89 补充一（2026-10-15 07:55）更正 D89
- D89 第 1、3、4、6 条撤回（未对照 D79，冲突），以 D79 及补充为准；D89-5 保留。
- check_blocked：维持 D79 补充五/七：check_type=marking_inspection，ctx {reason ∈ not_marked|pending|fail, marking_id(无主记录为 null), trace_code(未首打为 null)}，顶层与 results[] 一致；不使用 marking/mark_id。
- 模板请求体：lines 为字符串数组（白名单占位符）；按产品+客户绑定，请求体带 product_id、customer_id；响应带只读 product_name、customer_name、created_by。
- unknown_placeholder：loc ["body","lines",i]，i 为 0 起数组下标；ctx {reason:"unknown_placeholder", placeholder}，每个一条。
- 状态仅 draft|approved|retired，无 pending、无提交接口；审批 draft→approved，同模板原 approved 版本自动→retired（同时只有一个已批准版本）。approved/retired 编辑 409 template_readonly；草稿可改。
- preview/validate 的 lines 同为字符串数组（D79 补充七附注二）。

### D89 补充二（2026-10-15 07:57）
- 模板 code 租户内唯一；(tenant, product_id, customer_id) 也唯一，一个产品+客户只有一个模板，版本挂在其下。重复均沿用现有通用重复键错误。

## D90（2026-10-15 08:10）
1. 模板 product_id/customer_id 创建后不可改；PATCH 带不同值 422 value_error ctx.reason=immutable，同值视为未改。
2. 重复键本期保持 integrity() 409 + 字符串 detail；{code:"duplicate", message} 进格式统一批次。
3. 模板详情 data.versions[{version, status, created_by, created_at, approved_by, approved_at}]，version 倒序，未批准为 null。
4. 编辑只针对最新版本，删除「编辑 retired 409」用例；最新为 approved 时 409 template_readonly。
5. 通用导入：更新已有记录时空单元格（None/""/纯空白）及缺列一律不改，不写履历不发事件；清空走 API。新建时空单元格取默认值/null，必填报 missing。
6. 导入只改 certified_on：同 PATCH，写 changed 履历+事件，不要求原因；值未变不写。
7. 只读 403：8011 升级后由前端用 fe-it-ro 复跑记为覆盖。

## D91（2026-10-15 08:13，追溯/标签 TR-Q1~Q5）
1. 404 按 D86 字符串 detail，D84 Q4 code=not_found 待格式统一批次。
2. 追溯结果加 wafers[{wafer_id, slot}]（批次当前晶圆，无则 []）。
3. 标签比对对象：未作废主记录最新打印（seq 最大）的 trace_code；409 label_marking_mismatch ctx {reason:"mismatch", marking_id, expected, actual}。
4. 无未作废主记录或未首打：同 code，ctx.reason=not_marked，marking_id 按 D79（无则 null），expected=null。
5. X-Tenant-ID 非成员租户 403；跨租户追溯码 200 空列表。
6. code 缺失/空/纯空白 422 missing loc ["query","code"]；kind 非法 422 value_error loc ["query","kind"] ctx {reason:"invalid_choice", choices}。
- 注：D90-5 覆盖 D88 的留空 use_api；仅实际改变 is_active/expires_on 值时报 use_api。

### D91 补充一（2026-10-15 08:16）
1. 改绑定 immutable 属 D81「需记录的 422」，在 404 后、409 template_readonly 前；err_422 value_error，每字段一条，ctx {reason:"immutable"}。
2. 导入新建资质 expires_on 非必填，留空=永久有效。
3. opq-01 补：只改 certified_on 写 changed 履历+事件；值未变不写。

### D91 补充二（2026-10-15 08:28）
1. 模板请求体：code(≤64,租户内唯一)、product_id、customer_id、lines(字符串数组)、description(可选≤300)；无 name；date_code_basis/uses_bin 本期不加。
2. D90-3 versions 每项加 lines。

## D92（2026-10-15 09:47，B1 f64f1cc 待定点）
1. B1 提交的 frontend i18n 生成文件按例外接受（测试要求的生成产物），恢复后前端核对；D82 补充一原则不变。
2. 超长本期保持 string_too_long，转 value_error max_length 进格式统一批次。
3. 引用产品/客户不存在本期保持 404 product_not_found/customer_not_found，是否改 422 进格式统一批次。
4. 写接口平铺、详情 {data}，维持现状。
5. PATCH 显式 null=不改；单行长度上限、空行是否允许恢复后再定。

### D91 补充三（2026-10-15 10:12）
- 修订 D91-5：X-Tenant-ID 为未加入或不存在的租户，统一 404 "Tenant not found"（平台层现状，不暴露存在性）；trace-02 改断言 404。
