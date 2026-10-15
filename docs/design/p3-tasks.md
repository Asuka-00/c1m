# P3 任务卡（D51，依据 gap-list.md v0.3、decisions.md D53/D54/D58/D61、process/reviews/marking-rules.md）

版本：v0.1（2026-10-14 架构师草案）。P3 范围待 kai mi 定方向（D51），本稿先按 gap-list D 组剩余项 + P2 推迟项拆卡。P2 卡优先，P2 没有可领的卡再领 P3。

## 0. 通用约定（每张卡默认遵守，卡里不再重复）
- 分支：`be/p3`、`fe/p3`、`eap/p3`、`qa/p3`，从当前本地提交拉出，不推送、不部署；推送部署须 kai mi 批准（D51）。P1/P2 缺陷和复测优先。
- 权限码 `mes.<模块>:<动作>`；错误顺序 401/403 → 404 → 409（先权限，再对象存在，再状态冲突）；请求体非法 422，未知字段/只读字段 422（D34、D38）。
- 时间：库里 timestamptz，接口输出 UTC 带 Z（D45）；xlsx 导出按 D46/D54-4。
- 定点数：按字符串返回、去末尾零（D50）；输入接受字符串和数字，超过 6 位小数返回 422 `value_error`，不四舍五入（D60）。
- EAP 预留：可能由设备上报的记录带 `source` 和可空 `external_event_id`，唯一 (tenant_id, source, external_event_id)（D30、D54）。
- 领域事件：命名 `<聚合>.<过去式>`，先登记到 domain-events.md 再实现，经 `app.core.outbox.emit` 写入。
- 模块归属遵守 module-boundaries.md：光罩在 product（reticle 已在），人员资质在 execution（operator_qual 已在），报表只读查询，不新增反向依赖；打标新建 marking 目录。

## 1. 打标（D61；属推断，以客户打标规格书为准）

### P3-B1 打标模板（版本 + 审批）
- 范围 做：模板按「产品+客户」定义；字段：型号、日期码 YYWW（取值日期可配置：开批/打标/封装完成）、短追溯码、可选 bin；版本管理 draft→approved→retired，同一「产品+客户」只有一个生效版本。不做：图形化排版设计器。
- 数据模型：`mes_marking_template`（code、product_id、customer_id、version、status、lines JSON、date_code_basis、uses_bin、approved_by/at）。
- 接口：`/mes/marking-template` 增查改、`POST .../{id}/approve`、`/retire`。权限 `mes.marking:read/write/approve`。已批准版本只读，改动 409。
- 事件：`marking_template.approved`。
- 依赖：P2-B1–B4、B8 完成后开工。
- 验收：审批人不能是起草人（409）；改已批准版本 409；新版本批准后旧版本自动 retired。
- 估工时：2.5 人日。建议认领：后端。

### P3-B2 打标工步、发号与检验
- 范围 做：路线工步挂模板；模板含 bin 时保存路线校验打标工步在按 bin 拆批之后（否则 422 `marking_before_bin_split`）；出站时生成打标记录；系统发号，范围「客户+产品+日期码」唯一、不复用，发号对序列行加锁；打标后检验 pass/fail，不合格重打（沿用原号）或报废。不做：打标机通信。
- 数据模型：`mes_marking_seq`（customer_id、product_id、date_code、last_no）；`mes_marking_record`（lot_id、template_id+version、content 实际内容、trace_code、equipment_id、operator、marked_at、inspect_result、reprint_count、source、external_event_id）。
- 接口：`GET /mes/marking/preview?lot_id=`、`POST /mes/marking`（打标/重打）、`POST /mes/marking/{id}/inspect`。权限 `mes.marking:exec`。没有已批准模板 409 `marking_template_missing`。
- 事件：`lot.marked`、`lot.marking_inspected`。
- 依赖：P3-B1。
- 验收：并发 20 个请求发号不重号；重打号不变且 reprint_count+1；检验不合格未处理时不能出站（409）。
- 估工时：4 人日。建议认领：后端。

### P3-B3 打标追溯与出货标签一致性
- 范围 做：追溯支持 `kind=trace_code`，反查批次、谱系、晶圆；出货标签生成时比对打标内容，不一致 409 `label_marking_mismatch`。
- 依赖：P3-B2、P2-B2、P2-B4。权限沿用 `mes.exec:read`。
- 验收：追溯码查到晶圆 ID；标签内容与打标不符时不能打印。
- 估工时：1.5 人日。建议认领：后端。

## 2. 光罩（gap-list A：max_shots、产品层次匹配、履历）

### P3-E1 光罩数据模型草案
- 范围 做：复用 D53 耗材寿命模型（光罩专用状态枚举 `reticle_status`（D66）、`usage_count`/`effective_max_usage`、`warn_ratio`），不另起一套；光罩主数据（在现有 reticle 上扩展）、曝光次数计数、所在位置和状态（库位/机台/清洗/检查）、与机台挂载关系、适用产品+层次、检查记录（颗粒/雾化）。不做：通信实现。
- 验收：草案放 `eap/p3` docs 下，架构师审、后端评审通过；写明哪些计数可由 EAP 上报（source/external_event_id）。
- 估工时：1.5 人日。认领：设备集成（已认领 2026-10-14）。

### P3-B4 光罩寿命、匹配与履历（实现）
- 范围 做：按 E1 实现；进站检查新增 `reticle` 检查项：产品/层次不匹配、未挂载、状态不可用、达到上限 → 409 `check_blocked`（达上限 overridable=false，预警区间 200+警告，同 D54-5）；出站按次数累加曝光次数；检查记录。
- 接口：`/mes/reticle` 增查改、`POST .../{id}/mount`、`/unmount`、`POST /mes/reticle/{id}/inspection`。权限 `mes.reticle:read/write`。
- 事件：`reticle.mounted`、`reticle.unmounted`、`reticle.life_reached`。
- 依赖：P3-E1。
- 验收：同一光罩不能同时挂两台机台（409）；计数用定点字符串；履历可查。
- 估工时：3 人日。建议认领：后端。

### P3-F3 光罩管理页面
- 主数据、挂载/卸载、寿命条（黄/红同 FE-F8-2）、检查记录。依赖 P3-B4。2 人日。前端。

## 3. CT/Move 报表

### P3-F1 CT/Move 报表页面（先 mock）
- 范围：按工序、日期、产品筛选；趋势图 + 明细表；导出。前端在 `fe/p3` 用 mock，先发出假设的接口形状，架构师以此定契约。
- 验收：三语；日期按站点时区显示（D62），接口仍 UTC Z；空数据有空状态。
- 估工时：3 人日。认领：前端（已认领 2026-10-14）。

### P3-B5 CT/Move 报表接口
- **状态：可开工（D73）。** 契约以 D73 为准；口径按“D73/D74/D70 补充”：仅返工路线/工步出站算 rework move，另出 `rework_qty`；`by_operation` 加 `on_hold_lots`/`on_hold_qty`；Hold 时长按所在工序分摊。
- 范围 做：只读查询，基于 lot_history 计算：Move = 出站批次数/片数，按工序/日/产品聚合；工序 CT = 上一工序出站（首工序为开批）到本工序出站，返回平均、P50、P90。不做：批次 CT、数仓、预聚合表（性能不够再说）。
- 接口：`GET /api/v1/mes/exec/reports/ct-move`（契约按前端 `frontend/docs/p3-ct-move-contract.md` + D62/D63）。日期范围上限 92 天，超出 422 `date_range_too_large`。权限 `mes.exec:read`。批次 CT（开批到结批）不在 P3。不发事件。
- 依赖：P3-F1 接口形状。
- 验收：数量与 lot_history 手算一致；按日切分用站点时区（D54-4/D62）；撤销的转换不计入（D60）。
- 估工时：2.5 人日。建议认领：后端。

## 4. 人员资质（gap-list A：缺资质履历；考核记录不做，见 D62）

### P3-F2 人员资质页面（先 mock）
- 范围：资质列表、有效期、到期预警（30 天黄、过期红）、资质履历（考核记录不做）；进站资质不符的卡控提示三语。先发接口形状给架构师定契约。
- 估工时：2.5 人日。认领：前端（已认领 2026-10-14）。

### P3-B6 资质履历（D74）
- **状态：可开工（D74）。** 契约以 D74 为准（迁移 0033 `mes_operator_qual_log`）。补充：过期不自动停用，进站按 `expires_on` 硬拦；停用和延期必须填 `reason_id`（reason_type=operator_qual）和 `comment`，延期另需 `approved_by`，缺少时返回 422 `missing`；0033 履历表用 comment/reason_id/approved_by 三列。
- 范围 做：在现有 operator_qual 上加变更履历、即将到期汇总、预警天数单一来源；到期后进站检查 `operator_qual` 拦截（沿用现有检查项，409 `check_blocked`）。不做：培训课程管理。
- 接口：沿用已有 `operator_qual`、`operator_qualified`、`qual_expiry_notice`；新增资质履历和即将到期汇总接口，权限沿用现有 operator_qual 权限名。不做考核记录（D62）。
- 事件：`operator_qual.granted/renewed/changed/deactivated/expired`（D74）。
- 依赖：P3-F2 接口形状。
- 验收：过期资质进站被拦；履历可查；预警天数可配。
- 估工时：2 人日。建议认领：后端。

## 5. P2 推迟到 P3 的项

### P3-B7 寿命到期自动生成更换/PM 工单（D53-6）
- 范围 做：`tool.life_reached` / `reticle.life_reached` 触发时自动建一张待处理的更换或 PM 工单（同一工具未关闭工单只有一张）。不做：备件领用。
- 依赖：现有 PM 模块、P2-B10、P3-B4。权限 `mes.pm:write`（以后端现名为准）。
- 验收：重复事件不重复建单；工单关闭并换新后计数清零。
- 估工时：1.5 人日。建议认领：后端。**待工艺专家确认是否需要（开放问题 2）。**

### P3-B8 按报警等级拦进站（D58）
- 范围 做：报警码 `severity` 达到配置等级且未清除时，进站检查项 `alarm_severity`（off/warn/block 三档）拦截。不 Hold 批次（D58 补充）。
- 依赖：P2-B9、D58 对齐提交。
- 验收：清除报警后立即放行；未登记 ALID 不参与。
- 补充（D70 补充）：粒度沿用 `mes_alarm_code` 的“设备类型 + ALID”，单台覆盖为空时继承；迁移 0034 只在 mes_alarm_code 上加 `track_in_action`；只算 `cleared_at IS NULL` 的报警；P3 按整机拦截，子单元级拦截待定；初始分类按类别模板写进说明文档，不预置 ALID。
- 估工时：1.5 人日。建议认领：后端。按 D70 可以开工（等级是可配置的数据，初始配置由工艺专家给）。

### P3-B9 转换时记录原载具（D54-3）
- 范围：转换时记录母批原载具；撤销时提示原载具（不自动恢复）。
- 估工时：1 人日。建议认领：后端。**待评估，开放问题 4。**

### P3-F4 打标模板与打标作业页面
- 模板列表/编辑/审批、版本对比；作业页打标预览、检验、重打（填原因）；追溯页加追溯码类型。依赖 P3-B1–B3。3 人日。前端。

## 6. 设备集成其他
### P3-E2 评审
- 评审 P3-B2、B4 中带 source/external_event_id 的表，确认以后打标机、光刻机上报不改表结构。1 人日。设备集成。

## 7. 测试
### P3-Q1 P3 测试计划与验收用例
- 范围：`qa/plans/p3-test-plan.md`；覆盖每张卡验收要点和通用约定；重点：发号并发不重号、模板审批状态机、光罩寿命边界（同 D54-5）、报表数字与手算对账、资质到期拦截。光罩部分对照 P3-E1。
- 估工时：2 人日（计划）+ 随卡验收约 5 人日。认领：测试评审（已认领 2026-10-14）。

## 8. 依赖顺序
- 后端：P2 的 B1–B4、B8 完成后 → P3-B5、B6（契约定后）→ B1 → B2 → B3 → B4（E1 定稿后）→ B7；B8、B9 等确认。
- 设备集成：P2-E4 → P3-E1 → E2。
- 前端：F1、F2（mock）→ 联调 B5、B6 → F3 → F4。
- 测试：Q1 先出计划，随卡验收；P1/P2 复测优先。

## 9. 工时汇总（人日）
| 角色 | 卡 | 小计 |
|---|---|---|
| 后端 | B1 2.5、B2 4、B3 1.5、B4 3、B5 2.5、B6 2、B7 1.5、B8 1.5、B9 1 | 19.5 |
| 设备集成 | E1 1.5、E2 1 | 2.5 |
| 前端 | F1 3、F2 2.5、F3 2、F4 3 | 10.5 |
| 测试 | Q1 计划 2 + 随卡验收 5 | 7 |
| 合计 | | 39.5 |

## 10. 开放问题（待工艺专家 / kai mi 确认）
1. （kai mi）P3 范围是否就按本稿（打标、光罩、CT/Move、人员资质 + P2 推迟项）？是否还有要加或去掉的（D51）。
2. （工艺专家）寿命到期是否要自动生成更换/PM 工单，还是继续只拦开工 + 通知（D53-6）。
3. （工艺专家）按报警等级拦进站的等级划分和哪些设备类型适用（D58）。
4. （kai mi）撤销转换是否需要记录/提示原载具（D54-3），不需要则 P3-B9 取消。
5. （工艺专家）打标：客户打标规格书何时能拿到；日期码默认取哪个日期；短追溯码长度和字符集；重打次数是否设上限。
6. （工艺专家）光罩：曝光次数按 shot 还是按片计；颗粒检查周期和不合格处置；清除报警/检查后是否要 Qual（D53 遗留）。
7. （工艺专家）CT 口径：是否扣除 Hold 时间和排队时间；Move 按片还是按批。
8. （工艺专家）人员资质到期预警提前天数默认值（草案 30 天）；资质过期是硬拦还是可放行。

## 进度（2026-10-15 02:10）
- B1–B3：契约已定（D78/D79 及补充一至三），后端未开工，排在 B5、B6 之后。
- B4：已落地（be/p3），测试已通过。
- B5：进行中（后端，D73）。B6：B5 之后（D74）。B8：待开工（D58）。
- F4：`401da4c` 本地完成，在收 N-F1/N-F3；N-F2 按 D79 补充三改。
- E2：打标侧已定稿（eap/p3 `4f93f74`、sim `8a678bb`）；光罩侧进行中。

## 进度（2026-10-15 03:13，取代 02:10 版）
- B4 光罩：已落地，测试通过。
- B5 CT/Move：`2c19bb3` 复测有条件通过；修复提交 `59fb7c5`（P2-1、P3-1~3 + D77 补充一）在复测。
- D80 光罩幂等（14 接口 + 0035 迁移 + D82 补录时间）：后端进行中。
- B6 → B1 → B2 → B3：待开工（顺序见下）。B8 待开工。
- F4 打标页：`401da4c`/`245a721`/`31f266d` 已复核；D80 `64e063e`、D77 补充一 `3ce19d7`、B5 接入 `7bd1a4e` 待复核；D82 进行中。
- E2：打标侧定稿（sim `6aad82a`）；光罩侧预审定稿（`7bccae1`/sim `4bbc1a0`），等 D80 后端联调；先用 `59fb7c5` 跑现有场景。

## 待办卡 TODO-409：状态冲突 422→409（D82）
- 范围：P1/P2 中状态冲突返回 422 的 17 个接口（见 qa/reports/d81-p1p2-gap-inventory.md）。
- 先由前端盘点按状态码分支的文案处，后端出接口清单，三边同批。不进 P1/P2 收尾提交，P1/P2 推送后另议排期。

## B1→B2→B3 开工清单与验收要点（B6 之后）
B1 打标模板（D79 1/2/7）
- mes_marking_template + versions；lines 字符串数组，占位符白名单，未知 → 422 unknown_placeholder。
- 审批：起草人自批 422 self_approval；已批准版本只读 409 template_readonly；已有草稿 409 draft_exists。
- 权限 mes.marking_template:write / :approve；menu_keys.json 加菜单键。
- 验收：版本流转、自批拒绝、跨租户 404、D81 顺序。
B2 打标作业/发号/检验（D78 全部补充、D79 补充一~六、D81、config）
- POST /mes/marking 建主记录（每 lot 至多一条未作废，部分唯一索引）；/prints 发号（seq FOR UPDATE，重打需 reason_id+comment）；检验挂 print_id，最新一次为准；/void；GET /mes/marking/config（白名单校验、pattern_unsupported、迁移检查存量）。
- 出站 check_blocked：ctx.reason not_marked/pending/fail + marking_id；at_marking_step 只读字段；marked_at/last_printed_at（未首打为 null）。
- 错误 ctx：value_error + reason max_length/pattern；read_code 空/缺/null/空白 → missing。
- 事件 lot.marked / marking_inspected / marking_mismatched / marking_voided。
- 验收：QA 测试计划最新版打标用例全部通过（v0.10.2 为 95 条，MARK-01～95）+ 模拟器 marking 场景（去掉草稿跳过）对真实接口全过。
B3 追溯（D79 补充一）
- GET /mes/exec/trace?kind=trace_code，mes.exec:read，include_voided；结果形状按 D79 6。
- 验收：作废前后追溯、跨租户隔离、与出货标签一致性。
- TODO-409 补充（03:26）：范围以 QA 盘点表 G7 标记为准，work-order start/transition/undo-start 和 e10 都在内。409 一律对象格式 {code, message}，不再返回列表格式；QA 在 8012 验证后前端删旧格式兜底。后端排期时给出 e10 等的 code 清单。QA 回归脚本（run_p2/run_p2b）同提交改。

## 进度 04:12
- D80：be/p3 `f9e9dda` 已落地，后端自测 815 passed；QA 在 8012 复测中（结果未出）。EAP ret-report-08：105 步，76 通过 / 29 未实现 / 0 失败。
- 后端在做：D82 补充一（未挂载补录下机返回 409 invalid_transition）、D77 补充二（报表 range_inverted、严格 YYYY-MM-DD、撤掉 locales）、迁移内补授权（验收：只跑 alembic upgrade head 就能登录）。之后升级 8011。
- 前端：`98b5bb9` 冷启动修复已过 QA；`b32301e` 对齐 D80，待复核；在做 TODO-409 盘点文档和 F4 mock 对齐。
- EAP 光罩上报的 29 步：留到下一阶段（D67 不变），不放进 P3 补卡。设备集成出的接口草案作为下一阶段的输入，我评审后归档。
- 后端顺序：D82 补充一 / D77 补充二 / 授权（一个小提交）→ B6 → B1 → B2 → B3 → B8。迁移号：0033 给 B6，0034 给 B8，B1~B3 按合入顺序往后接；0035 的 down_revision 在合入时改接到当时的 head。（04:43：小提交后先做 0036 授权，再 B6）
- 迁移号更正（04:13）：取消为 B6/B8 预留 0033/0034。0035 保持接在 0032 后面，不改接；之后的迁移按合入顺序接在当时的 head 后面，编号从 0036 往后。已经升到 0035 的库不用恢复。

## 进度（05:09）
- 后端：`386c4e0` 复测通过（D82 补充一、D77 补充二）。在做的提交：0036 授权（D83）、conftest 不再调用角色脚本、D77 补充三报表日期、所有 date 字段统一返回 pattern（附字段清单）、只读账号 fe-it-ro。之后 B6 → B1 → B2 → B3 → B8。
- B5/D80：已复测通过（`f9e9dda` 及之后）。
- F4：`9f16d6b` 复测通过；`7395ff8`/`f41a39b`/`80a36a3` 在复核。下一步 F2 资质履历 mock，给 B6 用。
- E2：打标侧定稿；光罩侧 ret-report-09 对 `386c4e0` 通过 76 步，0 失败；29 步上报留到下一阶段。sim `b4e6b23`，marking-12 写接口加 key 在做。
- QA P3-a 已定为 D77 补充三。

## B6 验收要点（05:09 钉死）
- 迁移号按合入顺序接在 0036 后面（预计 0037），不再用 0033；表名 `mes_operator_qual_log`，包含 comment/reason_id/approved_by 三列；迁移里带上 app_user 授权（D83）。
- 资质过期后进站返回 409 check_blocked，results[] 里有一项 check_type=operator_qualified，ctx 带 qual 标识和 expires_on。过期不自动停用。
- 停用和延期缺 reason_id 或 comment 时返回 422 missing；延期缺 approved_by 也返回 422 missing；自己批准自己返回 422 self_approval。顺序遵循 D81，写接口需要 key。
- 授予、延期、变更、停用都在履历里留一条记录，并发出对应的 operator_qual.* 事件（D74）。履历时间用 UTC 带 Z，查询日期参数按 D77 补充三严格校验。
- 即将到期汇总的预警天数只从一个配置项读取，改配置后立即生效。
- 前端用 F2 mock 联调通过，QA 在 8012 上用无权限账号验证 403 排在最前。

## 进度（06:06）
- 后端：`a72b85b`（D83 和日期校验）已复测通过；`8d01a4a`（FOR ROLE 和 prestart）静态评审有条件通过；`1ef2eff` 之后正在做 B6（D85 及其补充、D86）。B6 之后是 B1 → B2 → B3 → B8（D84），再修 members/new 不是原子操作的 TODO。
- 前端：F2 资质 mock 做到 `226e802`（D85 补充二），在复核；下一步是 D86 的 mock 对齐小提交，然后做 F3 光罩管理页。B6 落地后用真实接口联调 F2。
- 设备集成：ret-report-10 基于 `8d01a4a`，光罩 105 步里通过 76、未实现 29、失败 0；opq-01 B6 草稿 `3d25b86`，按 D86 收紧，等 B6 落地后去掉跳过。8013 只读账号的事等 kai mi 回复。
- QA：在复核前端 `f9164fc`～`226e802`；P3-Q1 测试计划补进 D83 补充二、D85、D86 和补充一；B6 交付后复测 be/p3。
- 顺序：B6 → F2 联调 → B1/F3 并行 → B2 → B3 → B8。格式统一（reused 改数组、warnings[] 改新格式、光罩删除改成 ref_type/ref_count）等 P1/P2 推送后单独做一批。

## 进度 07:16
- B6 = be/p3 `40e4342`（迁移 0037，841 passed）；D87+补充一 = `ff79d22`（844 passed）。均未推送。
- D85 补充四、D87、D87 补充一～三、D88 已定。
- 前端：F3 光罩页 + D87 + QA P3 交到 `e35ca10`，QA 无遗留；正在做 F2 资质真实接口对齐（8011 升级前只对齐 mock）。
- 设备集成：ret-report-11（`38117bf`）、`ff7f0a8`（D87 key）；正在对 `ff79d22` 跑资质 opq-01 与光罩 D87 断言。
- QA：正在 8012 复测 `ff79d22`。
- 顺序：复测 ff79d22 → 8011 升级后 F2 联调 → D88-3 导入小提交 → B1 ∥ F3 收尾 → B2 → B3 → B8 → 推送后格式统一批次。

## 进度 07:38
- B6 `40e4342` + D87 `ff79d22` QA 复测通过（P1/P2/P3=0，844 passed，76 项 API）。待补：只读账号 403（随 D88-3 复测）。
- 设备集成：ret-report-12 全过；opq-01 `edebe1c`（11 条跳过由 QA 覆盖）。
- 前端 F2 5 个提交（36faef3..9393b15）QA 复核中；8011 升级中。
- 下一步：D88-3 小提交（导入拒绝 + history at Z）→ B1 ∥ F3 收尾 → B2 → B3 → B8。

### 进度 08:10
- D89 撤回 1/3/4/6，补充一/二回到 D79；D90 定改绑定、重复键、versions、导入留空、certified_on。
- 589fbbc 8012 复测不通过：P1-1 导入 is_active 留空写 NULL，后端 B1 后出修复小提交。
- 前端 2ede251、4731ed6、af75ae5 本地，待 QA 审；8011 F2 写联调完成。
- 设备集成 1c7178b（marking 回 D79，201 步跳过），待 QA 审；下一步 B3 追溯、B8 草稿。
- 后端：B1 进行中；CORS 暴露 Idempotent-Replayed 小提交。

### 进度 08:23（限额暂停）
- eap 8f38a4d+4b8f6e0 QA 通过（5 条 P3 延后）。前端修复提交、后端 B1/P1-1/CORS 三提交完成后全员暂停；B2/B3/B8、8011 升级、作业页/追溯页 mock 待恢复。
