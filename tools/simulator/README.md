# CIM 设备模拟器（P2-E5，模式 A）

把 YAML 场景里的设备事件（状态变化、报警、开工/出站、耗材计数、上料）翻译成 MES 现有 HTTP 接口调用，并断言返回码和错误 code。
设计见 `cim-team/eap/p2/equipment-simulator-design.md` v0.2，相关决定 D30、D43、D53。只调接口，不直接写 MES 表。

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
.venv/bin/python -m sim validate scenarios/*.yaml          # 只校验格式
.venv/bin/python -m sim run scenarios/*.yaml --target http://127.0.0.1:8013 --report out.report.json
```
- 默认只允许 `127.0.0.1`；`8010/8011/8012/5174/5184` 一律拒绝。`--allow-remote` 才放开非本机地址。
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
| `alarm_set {eq,alid,lots?,save_as?}` / `alarm_clear {eq,alarm:$名}` | B9 落地后的报警接口 | 适配层，接口不存在 -> skipped |
| `tool_usage {eq,tool,delta}` | B10 落地后的耗材计数接口 | delta 按字符串传（numeric） |
| `expect_hold {lot,source?,present?,count?}` | `GET /mes/exec/holds` | |
| `replay {eq,seq|from_seq,to_seq,expect:idempotent}` | 原样重发 | 要求同状态码、同记录 id |
| `precondition {eq?,qual_state?,e10?,lot?,lot_status?}` | 只读 | 不满足 -> skipped |

`expect` 默认 `{status: 200}`；`code` 取自 `detail.code`；`check` 在 `detail.results` 里按 `check_type` 找检查项并比较其余字段。

## 关键规则
- `external_event_id = sim:{run_id}:{设备}:{序号}`，序号按设备从 1 递增，同一场景重放 ID 完全相同；写请求同时带 `Idempotency-Key`。
- D30：走手工接口时**不传 `source`**。EAP 写入入口落地后改为 `source=simulator`（D53-4）。
- 可插拔适配层（`sim/adapters.py`）：每类事件列出候选路径，运行前读后端 `openapi.json`；需要的接口一个都不存在时，场景整体 skipped 并写明依赖的卡（B9/B10），不发任何写请求。B9/B10 定稿路径后只需改候选列表。

## 场景
| 文件 | 现状 |
|---|---|
| `e10-state-cycle.yaml` | 现在可跑：EAP-DA01 SBY→PRD→SBY（要求起始为 SBY） |
| `wait-qual-block.yaml` | 现在可跑：待 Qual 的 EAP-DA02 开工被 409 `check_blocked`/`eqp_wait_qual`/`overridable=false` 拦（D43），被拦请求不改状态，可重复跑 |
| `alarm-hold.yaml` | 等 B9：报警 → Hold（source=equipment）→ 重放不重复 Hold → 清除后 Hold 仍在 |
| `tool-life-block.yaml` | 等 B10：计数到上限 → 开工 409 `check_blocked`/`tool_life`/`overridable=false`（D53-5） |

场景里的设备/批次编码对应 8013（租户 it-eap）的测试数据，换环境时改编码即可。

## 测试
```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest -q
```
单元测试用内存假后端，不连网络。

## 未做
模式 B（HSMS）、时间偏移 `at`（目前解析后忽略、顺序执行）、乱序/断线场景。
