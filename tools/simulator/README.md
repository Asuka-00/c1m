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
| `alarm_clear {eq,alarm:$名}` | `POST /mes/eqp/alarms/{id}/clear`（B9） | 时间放 `cleared_at`。B9 没有按 ALID 清除的接口；D55「不是 active -> 200 cleared=false」用对已清除报警再 clear 来测 |
| `expect_alarm {alarm:$名,unregistered?,alarm_status?,alid?,lots?}` | `GET /mes/eqp/alarms/{id}`（B9） | 校验 `unregistered` 和 `data.lots`（mes_alarm_lot，D55 OQ-3） |
| `expect_e10 {eq,state?,save_as?,same_as?:$名}` | `GET /mes/eqp/board` | 记下/比较 E10 状态，验证「报警不改 E10」 |
| `tool_usage {eq,tool,delta,reason?}` | `POST /mes/eqp/tools/{tool_id}/usage`（B10） | delta 按字符串传（D50）；负数是调整，必须给 `reason`（reason_code 编码） |
| `tool_reset {tool,reason}` | `POST .../reset` | 计数清零，`reason` 是 reason_code 编码 |
| `tool_mount {eq,tool,port?}` | `POST .../mount` | |
| `tool_unmount {tool,reason}` / `tool_replace {tool,new_tool,reason}` | `POST .../unmount`、`.../replace` | reason：life_end/broken/pm/swap/other |
| `expect_tool_log {tool,log?:usage\|mounts,count?,last?}` | `GET .../usage`、`.../mounts` | `last` 比较最新一条（倒序） |
| `expect_hold {lot,source?,present?,count?}` | `GET /mes/exec/holds` | |
| `replay {eq,seq|from_seq,to_seq,expect:idempotent}` | 原样重发 | 要求同状态码、同记录 id |
| `precondition {eq?,qual_state?,e10?,lot?,lot_status?}` | 只读 | 不满足 -> skipped |

`expect` 默认 `{status: 200}`；`code` 取自 `detail.code`；`data` 按字段比较响应 `data`；`body` 按点号路径比较整个响应体（如 B9 清除的 `{cleared: false}`、B10 的 `{"tool.life_state": warning}`）；`check` 在 `detail.results` 里按 `check_type` 找检查项并比较其余字段。

## 关键规则
- `external_event_id = sim:{run_id}:{设备}:{序号}`，序号按设备从 1 递增，同一场景重放 ID 完全相同；写请求同时带 `Idempotency-Key`。
- D30：走手工接口时**不传 `source`**，MES 里记为 `manual`，靠 `Idempotency-Key` 防重复（D54）。
- **B11 模式（占位，默认关闭）**：D54 新增 EAP 写入入口 `POST /mes/eap/events`（P2-B11）。`--mode b11`（或 `SIM_MODE=b11`）时，`state`/`alarm_set`/`alarm_clear`/`tool_usage` 改发到这个入口，请求体 `{source: "simulator", external_event_id, event_type, equipment_id, payload}`，幂等键 (tenant, source, external_event_id)。后端没有这个入口时场景 skipped（依赖 B11）。请求体是猜的，B11 契约定稿后再对齐；在那之前请保持默认 `manual`。
- 可插拔适配层（`sim/adapters.py`）：每类事件列出候选路径，运行前读后端 `openapi.json`；需要的接口一个都不存在时，场景整体 skipped 并写明依赖的卡（B9/B10），不发任何写请求。B9（`0a74f8a`）、B10（`d27b700`）的路径已对齐。B10 的 reset/mount/unmount/replace 请求体严格、不收 `external_event_id`，模拟器标识放 comment 和 `Idempotency-Key`。

## 场景
| 文件 | 现状 |
|---|---|
| `e10-state-cycle.yaml` | 现在可跑：EAP-DA01 SBY→PRD→SBY（要求起始为 SBY） |
| `wait-qual-block.yaml` | 现在可跑：待 Qual 的 EAP-DA02 开工被 409 `check_blocked`/`eqp_wait_qual`/`overridable=false` 拦（D43），被拦请求不改状态，可重复跑 |
| `alarm-hold.yaml` | 等 B9：报警 → Hold（source=equipment）→ 重放不重复 Hold → 清除后 Hold 仍在 → clear 重放返回原记录；D55：无 active 报警 clear → 200 `cleared=false`；未登记 ALID → `unregistered=true`、写 `mes_alarm_lot`、不 Hold、不改 E10；事件时间超前 >5 分钟 → 422 `time_in_future` |
| `tool-life-block.yaml` | 等 B10（D54-5 修订版）：先 `reset` 清零；用量到 `max_usage × warn_ratio`（默认 0.9）进入预警区间，`track_in` 照常 200，警告只写进检查记录和批次履历，不需要放行；用量 `>= max_usage` 时 `track_in` 返回 409 `check_blocked`/`tool_life`/`overridable=false`（`move_in` 不判断）。前提 T-SIM-01 上限 1000、`warn_ratio` 0.9 |

场景里的设备/批次编码对应 8013（租户 it-eap）的测试数据，换环境时改编码即可。

## 测试
```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest -q
```
单元测试用内存假后端，不连网络。

## 未做
B9/B10/B11 的接口路径和请求体仍是猜的（`sim/adapters.py` 候选列表），契约定稿后对齐；模式 B（HSMS）、时间偏移 `at`（目前解析后忽略、顺序执行）、乱序/断线场景。
