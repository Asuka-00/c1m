# CIM 设备模拟器（P2-E5，模式 A）

把 YAML 场景里的设备事件（状态变化、报警、开工/出站、耗材计数、上料）翻译成 MES 现有 HTTP 接口调用，并断言返回码和错误 code。
设计见 `cim-team/eap/p2/equipment-simulator-design.md` v0.2，相关决定 D30、D43、D53、D54、D55。只调接口，不直接写 MES 表。

## 安装
```bash
cd tools/simulator
uv venv .venv && uv pip install -p .venv pyyaml pytest ruff
```
运行时只依赖 `pyyaml`（HTTP 用标准库）。

## 运行
```bash
export SIM_TENANT=<租户 id>            # X-Tenant-ID
export SIM_TOKEN=<令牌>                # 或者 SIM_USER + SIM_PASSWORD，启动时登录，令牌只在内存
export SIM_ALLOWED_PORTS=8013          # 端口白名单，必须显式给出
.venv/bin/python -m sim validate scenarios/*.yaml          # 只校验格式
.venv/bin/python -m sim run scenarios/*.yaml --target http://127.0.0.1:8013 --report out.report.json
```
- **端口白名单（D54）**：只允许 `127.0.0.1`/`localhost`，且端口必须列在 `SIM_ALLOWED_PORTS`（逗号分隔，如 `8012` 或 `8013,8014`）里；**默认为空 = 全部拒绝**，被拒时报错会写出当前白名单。只把自己的环境端口放进去（测试评审在自己环境用 `SIM_ALLOWED_PORTS=8012 ... --target http://127.0.0.1:8012`）。不再支持连非本机地址。
- **目标覆盖**：`--target` > 环境变量 `SIM_TARGET` > 场景里的 `target`。`run` 和 `validate` 都支持；`validate` 给了目标时会顺带检查白名单。
- 凭据只从环境变量读，不写文件；报告里不含令牌，凭据类字段一律打码。
- 退出码：有场景 failed 为 1，参数/场景错误为 2，其余（passed/skipped）为 0。

## 场景格式
```yaml
name: wait-qual-block
run_id: wait-qual-01            # 不能含冒号
target: http://127.0.0.1:8013
steps:
  - precondition: {eq: EAP-DA02, qual_state: wait_qual}   # 不满足 -> 场景 skipped
  - move_in:
      eq: EAP-DA02
      lot: FX0001
      expect: {status: 409, code: check_blocked, check: {check_type: eqp_wait_qual, overridable: false}}
```
| 步骤 | 接口 | 说明 |
|---|---|---|
| `state {eq,to,reason?}` | `POST /mes/eqp/{id}/e10` | E10 状态编码；接口不收 external_event_id，ID 写进 comment |
| `move_in/track_in/track_out {eq,lot,tools?,scrap?}` | `POST /mes/exec/lots/{id}/{stage}` | |
| `mount {eq,port,material_lot,save_as?}` / `unmount {mount:$名}` | `/mes/eqp/{id}/mount`、`/mes/eqp/mount/{id}/unmount` | mount 带 external_event_id |
| `alarm_set {eq,alid,lots?,save_as?,time_offset_s?}` | `POST /mes/eqp/{eq_id}/alarms`（B9） | 事件时间放 `set_at`；`time_offset_s` 往后推，测 D55 的 422 `time_in_future` |
| `alarm_clear {eq,alid}` | `POST /mes/eqp/alarms/clear`（B11 `8294b63` 新增的手工接口） | 按设备 + ALID 清除，时间放 `cleared_at`；没有 active 报警时 200 `{data:null, cleared:false}`（D55 OQ-5） |
| `alarm_clear {eq,alarm:$名}` | `POST /mes/eqp/alarms/{id}/clear`（B9） | 按报警 id 清除。b11 模式下改发 `alid`（取 `save_as` 时记下的 ALID），B11 不认 `alarm_id` |
| `expect_alarm {alarm:$名,unregistered?,alarm_status?,alid?,lots?}` | `GET /mes/eqp/alarms/{id}`（B9） | 校验 `unregistered` 和 `data.lots`（mes_alarm_lot，D55 OQ-3） |
| `expect_e10 {eq,state?,save_as?,same_as?:$名}` | `GET /mes/eqp/board` | 记下/比较 E10 状态，验证「报警不改 E10」 |
| `tool_usage {eq,tool,delta,reason?}` | `POST /mes/eqp/tools/{tool_id}/usage`（B10） | delta 按字符串传（D50）；负数是调整，必须给 `reason`（reason_code 编码） |
| `tool_reset {tool,reason}` | `POST .../reset` | 计数清零，`reason` 是 reason_code 编码 |
| `tool_mount {eq,tool,port?}` | `POST .../mount` | |
| `tool_unmount {tool,reason}` / `tool_replace {tool,new_tool,reason}` | `POST .../unmount`、`.../replace` | reason：life_end/broken/pm/swap/other |
| `expect_tool_log {tool,log?:usage\|mounts,count?,last?}` | `GET .../usage`、`.../mounts` | `last` 比较最新一条（倒序） |
| `expect_hold {lot,source?,present?,count?}` | `GET /mes/exec/holds` | |
| `replay {eq,seq|from_seq,to_seq,expect:idempotent}` | 原样重发 | 要求同状态码、同记录 id；`expect` 也可写成断言映射，如 `{body: {duplicate: true}}` |
| `reuse {eq,seq,change,expect?}` | 同一个幂等键换内容重发（D57） | manual 用原 `Idempotency-Key`/`external_event_id`，b11 用原事件号，把 `change` 改进请求体（b11 改进 `payload`；`to` 是 E10 状态编码简写）。默认期望 422 `idempotency_key_reused`；有没有写入用后面的 `expect_*` 步骤验证 |
| `seed_alarm_code {eq,alid,action,target_state?,extra?}` | `GET/POST/PATCH /mes/alarm_code` | D59 报警码种子（按设备 + ALID upsert 单台覆盖）。`action` 只有 `none`/`set_state`，`set_state` 必填 `target_state`（E10 状态编码）；给 `expect: {status: 422}` 测 D59 反例 |
| `expect_e10_history {eq,filter?,last:{to?,trigger?,source?}}` | `GET /mes/e10_history` | `filter` 作为查询参数（如 `trigger: equipment`，后端 f2d890c 起可用），结果每条都要符合；最新一条 E10 履历（D58 补充 `trigger`=manual/equipment/system，`source`=事件来源） |
| `expect_eap_read {entities?,denied?}` | 服务账号 `GET/POST/PATCH /mes/{entity}`、`/export` | D65 `mes.eap:read_master`：equipment / alarm_code / e10_state 列表、详情 200，新增 / 修改 / 导出 403；`denied` 里的实体读 403。不发 DELETE。没有 `SIM_SVC_*` 时跳过 |
| `expect_query_422 {path,params,field?}` | 只读 GET | D65：422 的 detail 是列表，`loc` 以 `query` 开头（给了 `field` 时等于 `[query, field]`） |
| `expect_alarm_list {eq,rows:{ALID:{...}}}` | `GET /mes/eqp/alarms` | D65：每行顶层带 `state_changed` / `state_skip_reason`，按 ALID 比较最新一行 |
| `tool_set {tool,fields}` | `PATCH /mes/tool/{id}` | 测试准备：`expiry_date` 可写相对天数（`-1` = 昨天）、`tool_status`（P2-D3 过期 / 不可用） |
| `precondition {eq?,qual_state?,e10?,lot?,lot_status?}` | 只读 | 不满足 -> skipped |

`expect` 默认 `{status: 200}`；`code` 取自 `detail.code`；`data` 按字段比较响应 `data`；`body` 按点号路径比较整个响应体（如 B9 清除的 `{cleared: false}`、B10 的 `{"tool.life_state": warning}`）；`check` 在 `detail.results` 里按 `check_type` 找检查项并比较其余字段（默认任一条满足；`all: true` 要求每条都满足，`min_count` 最少条数，`not_message` 任何一条 message 都不能包含该文本）。期望值可以按模式写成 `{manual: manual, b11: simulator}`（`expect_alarm`、`expect_e10_history`）。

## 关键规则
- `external_event_id = sim:{run_id}:{设备}:{序号}`，序号按设备从 1 递增，同一场景重放 ID 完全相同；写请求同时带 `Idempotency-Key`。
- D30：走手工接口时**不传 `source`**，MES 里记为 `manual`，靠 `Idempotency-Key` 防重复（D54）。
- **B11 模式**（已对齐后端 `8294b63`，默认仍是 manual）：`--mode b11`（或 `SIM_MODE=b11`）时，`state`/`alarm_set`/`alarm_clear`/`tool_usage` 改发到 `POST /mes/eap/events`，请求体 `{source: "simulator", external_event_id, event_type, equipment_id, payload}`，幂等键 (tenant, source, external_event_id)，不带 `Idempotency-Key`。
  - payload 严格校验：`external_event_id`、`equipment_id` 只放信封；`tool_usage` 的 `tool_id` 放进 payload；`alarm_clear` 只发 `alid`（不发 `alarm_id`）。
  - 响应是 `{data: 台账行, duplicate, result: 下层接口响应}`。模拟器断言和 `save_as` 用 `result`（和手工接口同形），`duplicate` 取信封上的（重放时 `result` 原样是首次的），台账行在 `event` 下。
  - 重放：200 `duplicate=true`、`result` 同首次；同事件号换内容：422 `idempotency_key_reused`，不写入（D57）。
  - **服务账号**：B11 需要权限 `mes.eap:write`，只在租户角色 **`eap_service`** 里；owner、admin、平台超级用户调用都是 403。运行 b11 模式前，请在目标租户里给模拟器专用账号分配 `eap_service` 角色，用它的 `SIM_USER`/`SIM_PASSWORD`（运行时注入，不写文件、不打印）或 `SIM_TOKEN`。manual 模式不需要这个角色。
  - 后端没有这个入口时场景 skipped（依赖 B11）。
  - D65：EAP 账号只能有 `eap_service`（不得挂 admin）。设 `SIM_SVC_USER`/`SIM_SVC_PASSWORD`（或 `SIM_SVC_TOKEN`）后，B11 事件和 `expect_eap_read` 用这个服务账号；按编码查主数据、进站、工具、报警码种子等测试准备仍用主账号 `SIM_USER`。
- 422 解析同时接受字符串 detail 和列表 detail（`expect.message` 按 msg 子串匹配两种都行；`loc`/`type` 只认列表）。`replay` 可加 `same_as_first: [字段]`（P2-D8）和 `body`。
- **D57 Idempotency-Key**：manual 模式下 E10（`/mes/eqp/{id}/e10`）和工序（`/mes/exec/lots/{id}/{stage}`）请求都带 `Idempotency-Key = external_event_id`；同键同内容重放返回首次响应（SBY→SBY 不再 422），同键换内容 422 `idempotency_key_reused`。
- 可插拔适配层（`sim/adapters.py`）：每类事件列出候选路径，运行前读后端 `openapi.json`；需要的接口一个都不存在时，场景整体 skipped 并写明依赖的卡（B9/B10），不发任何写请求。B9（`0a74f8a`）、B10（`d27b700`）的路径已对齐。B10 的 reset/mount/unmount/replace 请求体严格、不收 `external_event_id`，模拟器标识放 comment 和 `Idempotency-Key`。

## 场景
| 文件 | 现状 |
|---|---|
| `e10-state-cycle.yaml` | 现在可跑：EAP-DA01 SBY→PRD→SBY（要求起始为 SBY） |
| `wait-qual-block.yaml` | 现在可跑：待 Qual 的 EAP-DA02 开工被 409 `check_blocked`/`eqp_wait_qual`/`overridable=false` 拦（D43），被拦请求不改状态，可重复跑 |
| `alarm-udt-block.yaml`（原名 `alarm-hold.yaml`，D58 后改名，旧文件名不再保留） | 等 B9 + B11（manual 要 `/mes/eqp/alarms/clear`）。D58：报警（含未登记 ALID）只记录、关联批次，**不 Hold、不拦进站**；报警影响进站只走设备状态。流程：FX0002 move_in → 报警 1001 set（重放不重复）→ 断言没有 Hold、E10 仍 SBY → 状态事件切 UDT（D57 反例：同键换目标状态 422、状态不变；同键同内容重放返回首次响应）→ track_in 被 409 `check_blocked`/`e10_available` 拦 → OQ-5 ① 按 ALID 清除 `cleared=true`，E10 仍是 UDT（清除不自动恢复）→ OQ-5 ② 无 active（已清除的 1001、从未上报的 9998）200 `cleared=false`、`data=null` → 状态切回 SBY → track_in 200 → OQ-5 ③ 未登记 ALID 9999：`unregistered=true`、写 `mes_alarm_lot`、不 Hold、不改 E10，按 ALID 清除 `cleared=true`；事件时间超前 >5 分钟 → 422 `time_in_future`。前提：EAP-DA01 起始 SBY 且工步配了 `e10_available` 检查、FX0002 waiting；跑完 FX0002 已进站，不能原样重跑 |
| `idempotency-d57.yaml` | 等 B10 + D57：E10 同键换目标状态 → 422 `idempotency_key_reused`、状态不变、同键同内容重放返回首次响应；usage 同事件号换 delta → 422、履历不变，重放 `duplicate=true`。要求 EAP-DA01 起始 SBY，结束时回到 SBY |
| `tool-life-block.yaml` | 等 B10（D54-5 修订版）：先 `reset` 清零；用量到 `max_usage × warn_ratio`（默认 0.9）进入预警区间，`track_in` 照常 200，警告只写进检查记录和批次履历，不需要放行；用量 `>= max_usage` 时 `track_in` 返回 409 `check_blocked`/`tool_life`/`overridable=false`（`move_in` 不判断）。额外断言 `tool.effective_max_usage="1000"`、`tool.effective_warn_ratio="0.9"`（`23c502d`），usage 同事件号换 delta → 422 且不写入。前提 T-SIM-01 上限 1000、`warn_ratio` 0.9 |

场景里的设备/批次编码对应 8013（租户 it-eap）的测试数据，换环境时改编码即可。

## 测试
```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest -q
```
单元测试用内存假后端，不连网络。

## 未做
B9（`0a74f8a`）、B10（`d27b700`/`23c502d`）、B11（`8294b63`）已对齐；还没对真实后端跑过 b11 模式（8013 还没部署 B11）。模式 B（HSMS）、时间偏移 `at`（目前解析后忽略、顺序执行）、乱序/断线场景。

### 422 统一格式（后端 1a7c0fb）
- 模拟器对见到的每个 422 都检查：detail 为非空列表时逐项必须带 `code`（无专用码时 code = type）；detail 为对象时对象须带 `code`。不满足即该步失败（`Runner(strict_422=True)`，默认开）。
- detail 不是列表（目前只有 D57 `idempotency_key_reused`）不判失败，在报告该步记 `warn_422`。
- `expect_query_422` 新增 `loc`（如 `[path, field]`）、`code`、`code_is_type`；params 值 `$eq:CODE` 解析为设备 id。
- `expect_eap_read` 新增 `allowed_paths`：服务账号对这些路径 GET 须 200（如 `/mes/_meta`）。

### D65 补充 4：请求体未知字段一律 422 unknown_field
- `idempotency_key_reused` 的对象格式 `{code, message}` 是认可的旧格式，不再记 `warn_422`。
- 新步骤 `expect_body_422`（目前 endpoint=e10）：`POST /mes/eqp/{id}/e10` 带未知字段期望 422 `unknown_field`、loc `[body, 字段]`；`to` 填设备当前状态，后端不拦时只会报原地迁移，不改状态。
- 步骤可标 `xfail: 原因`：失败只记 xfail，不判场景失败；通过记 `xpass`（说明后端已修，可去掉 xfail）。`--strict-xfail` 或 `SIM_XFAIL=0` 时按普通步骤判。e10-state-cycle 的未知字段断言对 1a7c0fb 标了 xfail。
- `tests/test_body_audit.py`：所有场景在两种模式下发出的请求体逐个对照后端请求模型字段表，有多余字段即失败。

### 后端 56474fe（含 a888370）
- e10 未知字段断言去掉 xfail，必须通过（xfail 机制保留，供以后用）。
- `expect_body_422` 支持 `endpoint: move_in|track_in` + `lot`：未知字段期望 422 `unknown_field` `[body, 字段]`，前后比对批次行确认无副作用（tool-life-block 里用 move_in）。
- 新步骤 `expect_eap_envelope_extra`：服务账号向 `/mes/eap/events` 发按 ALID 清除，`comment` 放信封顶层（D54 并进 payload），期望不 422（无 active 报警 -> cleared=false，无副作用）；没有服务账号时记 skip。
- 请求体审计：`/mes/eap/events` 按“顶层多余字段并进 payload”后的 payload 审计。

### P3 草稿场景（分支 eap/p3-sim）
- `scenarios/p3-draft/`：光罩曝光计数上报、碰撞 → Hold，依据 P3-E1 草案 v0.8.2（D66～D69 及补充）。场景顶层 `draft: 原因` → 整体 skipped，不连后端。
- 草稿步骤（`reticle_mount`、`reticle_usage`、`reticle_incident`、`reticle_adjust`、`reticle_hold`、`reticle_release`、`reticle_restore`、`reticle_scrap`、`reticle_unmount`、`expect_reticle`、`expect_reticle_history`）只做格式校验，P3-B4 落地前执行会失败；落地后按 openapi 校正路径与字段，再实现。
- `scenarios/*.yaml` 不含草稿目录，现有 5 个场景和请求体审计不受影响。
- **重放（G-3）**：现有 `replay: {eq, seq}` 只重发按设备序号记下的事件步骤（state/stage/alarm/tool_usage 等，带原 `Idempotency-Key` 或 `external_event_id`），草稿光罩步骤不进这个序号。光罩草稿改用 `reticle_replay: {of: <save_as 名>, change?: {...}}`：对 `save_as` 记下的那次请求**用同一个 `Idempotency-Key`（B11 为同一个 external_event_id）、同一路径**再发一次（如 `/mes/reticle/{id}/usage`、`/incident`）；给 `change` 时改请求体，期望 422 `idempotency_key_reused`。P3-B4 落地后在 runner 实现。

### P3-B8 草稿：按报警等级拦进站（D58 + D70）
- `scenarios/p3-draft/alarm-track-in-action.yaml`：off / warn / block 各一遍；warn+block 同时未清除取 block，清掉 block 变 warn；未登记 ALID 不拦；清除后立即放行；每次进站后 `expect_hold present=false`。复用 `seed_alarm_code`、`alarm_set`、`alarm_clear`、`track_in`、`expect_hold`。
- `scenarios/p3-draft/marking-report.yaml`（P3-E2 打标，按 D78 补充一至五、D79 及补充一二、E7，等 P3-B1/B2/B3）：同一打印可多次检验、以最新为准，出站后检验 409；read_code 不校验格式（空 missing、>128 码点 max_length）；长度按码点；未检验也可重打（须填原因）；marked_at=首打、last_printed_at=最近打印、筛选只认首打；`sim/marking.py` 的 pattern_allowed 按白名单收紧、另有 check_read_code；EAP 上报找不到未作废主记录 409 no_active_marking；产品绑定已批准模板才查出站（not_marked/pending/fail 带 ctx.reason，未绑定放行）；POST /mes/marking 只建主记录、打印（含首打）走 /prints；同批次再建 409 already_marked、作废后可重建（seq 从 1）；pass 但读回码不一致强制 fail（result_overridden）；追溯 kind=trace_code 默认不含作废、include_voided=true 才含；列表 marked_at_from/_to 半开区间；trace_code 空串/纯空白只报一条 missing、小写/首尾空格报 pattern（不规范化；本地预校验 `sim/marking.py` 用 config 正则全串匹配）；lot.marked 的 reason_id 在 seq=1 时为 null；先读 `GET /mes/marking/config` 作 trace_code 422 期望值（逐条 ctx.max_length / ctx.pattern；EAP 上报 422 不 409、不写 audit、不发事件）；void 必须带 Idempotency-Key、无 `mes.marking:void` 403；lot.marked / marking_inspected / marking_voided / marking_mismatched payload 断言；主记录（只读 reprint_count、latest_inspection_status）+ `mes_marking_print`（seq 连续，duplicate/重放不占 seq）+ `mes_marking_inspection`（挂 print_id）；缺 Idempotency-Key 422 missing（loc=[header, Idempotency-Key]）、手工重放无 duplicate 字段、trace_code 422 value_error ctx.reason=max_length/pattern（手工和 EAP 两入口）、trace_code_mismatch 409、OCR 不一致 fail + lot.marking_mismatched、出站只看最新打印的最新检验（pending/fail 409 check_blocked，pass 放行）、作废 /void 缺原因 422、作废或批次报废后 409 invalid_transition。`marking_create`、`marking_print`、`marking_inspect`、`marking_void`、`marking_report`、`marking_replay`、`marking_config`、`expect_marking*`、`lot_scrap` 均为草稿步骤。
- 草稿步骤（**B8 落地后核对**）：`set_track_in_action {eq, alid, value}`（适配器 `alarm_track_in_action`，路径先按通用 CRUD `PATCH /mes/alarm_code/{rid}` 提议）、`expect_alarm_code {eq, alid, fields}`。
- 待核对：warn 警告在 200 响应里的位置（场景里先写 `warning: {check_type, alid}` / `absent_warning`）、block 的 `results[]` 每项字段、工步检查项名（是否叫 `alarm_severity`）、一台机台多个报警时 details 是否列出全部 ALID。
- **D70 补充（6f31ec7 之后）**：warn 读进站 200 的 `warnings[]`（`{code: alarm_severity, ctx.alarms[]}`）；block 读 409 的 `ctx.alarms[]`（`{alid, alarm_code, track_in_action}`，block 在前、同档按发生时间）、`ctx.reason=alarm_severity`；改配置 `PATCH /mes/alarm_code/{rid}`，非法值 422 `enum`（`ctx.expected=[off,warn,block]`）；类型层传 null 422，单台覆盖层传 null 清空改继承；只读 `effective_track_in_action` 及其来源 `effective_track_in_action_source`（`equipment` / `equipment_type`）用 `expect_effective_track_in_action {value, source}` 断言；覆盖层优先用例 ALID 2105；`set_track_in_action as: svc` 断言 eap_service 403。

### P3-B4 光罩草稿对照 335db8a（P3-E2）
- 事件不在 `/mes/reticle/{id}/history` 里：后端按 D71 记在 audit_log（action=事件名，changes.payload），草稿改用 `expect_reticle_events`（适配器 `reticle_events` → `GET /mes/audit_log?entity_type=reticle&record_id=…`）。
- 履历条目 `type` 取值 `mount`/`usage`/`inspection`/`incident`/`status`；卸载与挂载是同一行；状态行字段 `from_status`/`to_status`/`action`/`reason`/`username`/`at`（D71）。草稿用 `latest_of` + `fields`。
- `incident` 返回 201（重放也是 201）；`mount` 响应 `data` 是挂载记录；请求体 `slot` → `slot_code`、`reason`（调整）→ `reason_id`。
- D71：先 `invalid_transition` 后 `still_mounted`（335db8a 顺序相反，等下个提交）；超 6 位小数 422 `value_error`、`ctx.max_places=6`（335db8a ctx 尚无 max_places）。
- **D70 补充（两层一致性）**：单台覆盖行必须先有对应的类型行；草稿先建类型行再建单台行。反例：缺类型行 422 `value_error` `ctx.reason=type_row_missing`；设备无设备类型 422 `value_error` `ctx.reason=equipment_type_missing`（测试设备 EAP-NT01）；删除仍被引用的类型行 409 `referenced`（草稿步骤 `delete_alarm_code`，适配器 `alarm_code_delete`，B8 落地后核对）。
