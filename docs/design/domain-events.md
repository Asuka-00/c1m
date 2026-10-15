# fsft MES 领域事件出口（outbox）设计（优化清单第 10 项）

> 状态：v0.2，已按 decisions.md D1–D11 及「测试评审 19 处问题的处理」修订 · 作者：CIM 架构师 · 2026-10-13
> 本期只做"写出"：业务事务内写 outbox 表，**没有任何消费者和分发器**。

## 1. 现状与定位

- 现有 `execution/events.py`、`equipment/events.py` 用的是 `app.platform.notification`（`register_event` + `notify`），是**给人看的站内通知**（Q-Time 预警、自动 Hold、OOS）。它保留不动。
- 本设计的 outbox 是**给系统看的领域事件**：记录"发生了什么业务事实"，以后供 SSE 看板、EAP、SPC 订阅。两者不合并；以后通知可以变成 outbox 的一个消费者。
- 数据库：PostgreSQL（项目已用 JSONB、RLS，见 `app/core/rls.py`）。

## 2. 表结构 `mes_outbox`

```sql
CREATE TABLE mes_outbox (
    seq            BIGSERIAL PRIMARY KEY,            -- 全局递增，供消费者按序拉取 / SSE Last-Event-ID
    event_id       UUID        NOT NULL UNIQUE,      -- 幂等键，uuid7（时间有序）
    event_type     VARCHAR(64) NOT NULL,             -- 'lot.tracked_in' 等，见 §4
    schema_version SMALLINT    NOT NULL DEFAULT 1,   -- payload 结构版本
    aggregate_type VARCHAR(32) NOT NULL,             -- 'lot' | 'equipment'（Hold 事件归 'lot'，P03）
    aggregate_id   UUID        NOT NULL,
    version        BIGINT      NOT NULL,             -- 聚合版本，见 §2.1
    tenant_id      UUID        NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL,             -- 业务发生时间（与 lot_history.at 同值）
    actor          VARCHAR(100),                     -- 操作人用户名 / 'system'
    correlation_id UUID,                             -- 同一请求产生的多个事件共用（如合批）
    payload        JSONB       NOT NULL,
    published_at   TIMESTAMPTZ,                      -- 本期恒为 NULL；分发器上线后填写
    CONSTRAINT uq_outbox_agg_ver UNIQUE (tenant_id, aggregate_type, aggregate_id, version)
);
CREATE INDEX ix_outbox_unpublished ON mes_outbox (seq) WHERE published_at IS NULL;
CREATE INDEX ix_outbox_tenant_seq  ON mes_outbox (tenant_id, seq);
CREATE INDEX ix_outbox_aggregate   ON mes_outbox (aggregate_type, aggregate_id, version);
-- RLS 按 tenant_id，与其他业务表一致（沿用 app/core/rls.py 的策略生成方式）
```

字段说明：前端要求的"事件类型、对象 ID、版本号"分别是 event_type、aggregate_id、version；外加 event_id（去重）、tenant_id、occurred_at。`seq` 是新增的，便于以后按顺序推送和断点续传。

### 2.1 version 怎么来
- 给 `lot`、`equipment` 表各加一列 `row_version BIGINT NOT NULL DEFAULT 0`。
- **规则（P04/P06/P08/P18）：每发一个事件，该聚合 row_version 加 1，事件 version 取新值；不发事件的动作不加。** 一次动作对同一聚合发 n 条事件就加 n。因此 E05"version 连续无空洞"成立。
- 开批：0→1，`lot.created` 的 version=1；拆批子批同样从 1 开始。
- 每次 hold/release（包括不改变 on_hold 的第二条 Hold、释放非最后一条）都发事件并 +1。
- 因为调用前已 `SELECT ... FOR UPDATE`，版本单调且无并发冲突；`uq_outbox_agg_ver` 唯一约束兜底，重复写会直接报错回滚。
- 副作用：`row_version` 也可以给前端做乐观并发（列表页拿到的版本 ≠ 当前版本时提示刷新）。
- lot_hold 事件的聚合归到 `lot`（aggregate_type='lot'），版本用 lot 的 row_version，保证同一批次的所有事件有全序。

### 2.2 保留与清理
本期无消费者，表只增不减。加一个每日任务：删除 `occurred_at < now() - 30 天` 的行（天数可配置）。分发器上线后改为只删 `published_at IS NOT NULL` 的。

## 3. 同事务写入 API

位置：`app/core/outbox.py`（基础设施，所有模块可用；不放进某个 mes 模块，避免依赖方向问题）。

```python
def emit(
    s: Session,
    tid: uuid.UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    version: int,
    payload: Mapping[str, Any],
    *,
    occurred_at: datetime | None = None,
    actor: str | None = None,
    correlation_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """在当前会话的事务中插入一条 outbox 记录，返回 event_id。
    - 绝不 commit / flush 以外的操作；事务提交则事件可见，回滚则一起消失。
    - event_type 必须已在 EVENT_TYPES 注册，payload 用注册的 pydantic 模型校验。
    """

EVENT_TYPES: dict[str, type[BaseModel]] = {}
def register(event_type: str, model: type[BaseModel]) -> None: ...

@contextmanager
def correlation(cid: uuid.UUID | None = None): ...   # contextvar，合批等一次请求多事件时共享
```

调用约定：
1. 业务代码**不直接调用 emit**，由 `lot.state.transition()`、`lot.state.recompute_hold()`、`equipment` 的 E10 变更函数内部调用。这样"改状态"和"发事件"不可能分离。
2. **前提：service 内部不再 `s.commit()`**（现在 stages.py 7 处、hold.py 2 处等都在函数内提交）。改为路由层/用例层提交一次（module-boundaries.md 迁移第 7 步）。在此之前，emit 已经与状态写入处于同一个事务——因为 emit 发生在函数内 commit 之前——所以不阻塞本项落地，但批量接口 `batch.py` 的 `s.rollback()` 必须先改成 savepoint，否则会把前面批次已提交之外的事件一起回滚（实际行为正确，但语义要靠测试锁定）。
3. 只读接口、preview（如 `merge(..., preview=True)` 会 commit 但不改数据）不得 emit。

## 4. 首批事件类型

公共信封字段不再重复写进 payload。payload 全部是"变化后的事实快照 + 必要的变化前值"，ID 用字符串，时间用 ISO8601。

| event_type | aggregate | 触发点（改造后） | payload |
|---|---|---|---|
| `lot.moved_in` | lot | transition("move_in") | `{lot_code, step_id, step_seq, from_status, to_status, equipment_id}` |
| `lot.tracked_in` | lot | transition("track_in") | `{lot_code, step_id, step_seq, from_status, to_status, equipment_id, equipment_code, recipe_id, chamber_ids[], qty}` |
| `lot.tracked_out` | lot | transition("track_out") | `{lot_code, step_id, step_seq, from_status, to_status, equipment_id, qty, scrapped_qty_delta, rework_pending}` |
| `lot.moved_out` | lot | transition("move_out") | `{lot_code, from_step_id, to_step_id \| null, from_status, to_status, rework: bool}`（to_status=completed 表示完工）|
| `lot.held` | lot | hold_lot → recompute_hold | `{lot_code, hold_id, reason_code, hold_type, source, step_id, active_hold_count}` |
| `lot.released` | lot | release_hold → recompute_hold | `{lot_code, hold_id, release_reason_code, active_hold_count, on_hold}` |
| `lot.split` | lot（母批） | split（名词形式即过去分词，保持不变） | `{lot_code, children:[{lot_id, lot_code, qty, unit_codes[]}], parent_qty_after}` |
| `lot.created` | lot（每个子批一条）| split / start | `{lot_code, origin: "split"\|"start", parent_lot_id?, work_order_id?, qty, status, on_hold}` |
| `lot.merged` | lot（目标批）| merge | `{lot_code, sources:[{lot_id, lot_code, qty}], qty_after}` |
| `lot.terminated` | lot（每个源批一条）| merge / adjust 报废至 0 / qtime_scrap / track_out 全报废（紧跟 tracked_out 之后）| `{lot_code, to_status: "merged"\|"scrapped", into_lot_id?, reason: "merge"\|"adjust"\|"qtime"\|"track_out_all_scrap"}` |
| `lot.creation_reverted` | lot | undo_start（删除前，P09）| `{lot_code, work_order_id, qty}` |
| `lot.stored` | lot | store（仅满额入库 completed→stored 时；部分入库不发，P10）| `{lot_id, warehouse_id, location, qty, stored_at}` |
| `equipment.state_changed` | equipment | `e10_apply`、`e10_change` | `{equipment_code, from_state, to_state, e10_category, trigger: "auto"\|"manual"\|"equipment"（equipment=设备自报，本期预留不实现）, trigger_event?: "track_in"\|..., lot_id?, reason_code?}` |

同一请求产生的多条事件（如合批：1 条 merged + N 条 terminated + 设备无关）共享 `correlation_id`。

命名规则（P07）：事件名一律 `<聚合>.<过去式>`，以本表为唯一来源；`lot.state` 中用 `EVENTS: dict[action, tuple[event_type,...]]` 映射（move_in→lot.moved_in，track_in→lot.tracked_in，track_out→lot.tracked_out，move_out→lot.moved_out，hold→lot.held，release→lot.released，start→lot.created，undo_start→lot.creation_reverted，store→lot.stored 等），不得用 `lot.<action>` 拼接。

本期**不做**（不发事件，也不加 row_version）：部分晶圆 scrap、adjust 部分数量、jump、carrier、priority、部分入库、工单状态事件。以后打开时只需在 EVENTS 里加映射。

## 5. 测试要求（交给测试评审）

| 编号 | 用例 |
|---|---|
| E01 | 每个首批动作成功后，outbox 恰好新增预期条数，event_type / aggregate_id / tenant_id / payload 字段正确，payload 通过注册模型校验 |
| E02 | **回滚不写事件**：动作中途抛异常（如检查阻断 CheckBlocked、422 非法转移、模拟 DB 错误）→ outbox 无新行 |
| E03 | 批量过站中一批失败 → 失败批次无事件，成功批次有事件 |
| E04 | preview / 只读接口不产生事件 |
| E05 | **幂等/唯一**（不发事件的动作不加版本，故可严格断言）：同一 aggregate 的 version 严格递增无空洞（按 seq 排序后 version 连续）；人为重复插入同 `(aggregate, version)` 或同 event_id → 唯一约束失败 |
| E06 | 并发：两个会话同时对同一批次操作 → 事件 version 不重复，顺序与 lot_history 一致 |
| E07 | 租户隔离：A 租户会话查不到 B 租户事件（RLS） |
| E08 | 消费者侧幂等契约（为将来准备）：提供 `processed_events(consumer, event_id)` 表的示例消费者测试，同一事件投递两次只处理一次（本期可用测试替身实现）|
| E09 | 静态检查：`mes_outbox` 只能经 `app.core.outbox.emit` 写入 |

## 6. 以后如何挂消费者（本期不做，仅说明扩展点）

```
业务事务 ──写──> mes_outbox ──(分发器 relay)──> ① SSE 推送网关 → 前端看板
                                         ├──> ② EAP 适配进程（HTTP/MQ）
                                         └──> ③ SPC 模块（进程内 handler）
```

- **分发器**：独立后台任务，`SELECT ... WHERE published_at IS NULL ORDER BY seq LIMIT 500 FOR UPDATE SKIP LOCKED`，投递后置 `published_at`。可先用 PG `LISTEN/NOTIFY`（emit 时 `pg_notify('mes_outbox', seq)`）降低延迟，轮询兜底。保证"至少一次"，消费者用 event_id 去重。
- **SSE**：`GET /api/mes/events/stream?types=lot.*,equipment.*`，按 tenant 过滤，支持 `Last-Event-ID = seq` 断线续传。前端第 14 项的数据源 hook 收到 `{event_type, aggregate_id, version}` 后只失效对应查询，version ≤ 本地版本则忽略。
- **EAP**：设备侧"上报"走反方向——EAP 调 MES 接口（如 `equipment.e10_change`、`track_in`），MES 照常 emit；MES 对设备的指令（远程命令）订阅 `lot.held` 等事件后下发。EAP 作为独立进程，只通过接口和事件交互，不访问 MES 表。
- **SPC**：订阅 `lot.tracked_out` 拉取量测数据；判异后调用 `execution.service.hold_lot(source="spc")`，自然产生 `lot.held` 事件，形成闭环。
- 以后需要 MQ（Kafka/NATS/Redis Streams）时，只是分发器的投递目标变化，业务代码和 outbox 表不变。

## 7. 落地步骤
1. Alembic 迁移：建 `mes_outbox`，`lot/equipment` 加 `row_version`（迁移按模块命名，配合第 8 项）。
2. `app/core/outbox.py` + 事件 payload 模型注册。
3. 在 `lot.state.transition/recompute_hold` 和 E10 变更函数里接入 emit（依赖第 3 项状态机）。
4. 测试 E01–E09；清理任务。

## 8. 需要 kai mi 决定（Q1–Q4 已按建议定稿，见 decisions.md D7–D10）
- Q1 是否同意给 `lot`、`equipment` 加 `row_version` 列（版本号来源）？替代方案是用 `lot_history` 计数，但更慢且不适合 equipment。建议**加列**。
- Q2 outbox 保留天数，建议 30 天。
- Q3 首批是否顺带包含 `lot.stored`（入库）和 `lot.created`（开批）？建议**包含**，几乎零成本。
- Q4 是否同意把"service 内不 commit、由路由层统一提交"列为本期任务（对 outbox 正确性和批量操作 savepoint 都有好处，但改动面大）？建议**列入，放在状态机之后**。

## 9. CI
并发与 RLS 相关用例（E06/E07、状态机 C 组）在 CI 的 PostgreSQL service 中运行，不用 SQLite（P19）。

- `reticle.incident_recorded`（D66/D67）
- `reticle.restored`（D67）
- `reticle.held`（D68）
- `reticle.released`（D68）
- `reticle.life_reset`（D68）
- `reticle.mounted` / `reticle.unmounted` / `reticle.life_reached` / `reticle.inspected` / `reticle.inspection_failed` / `reticle.scrapped` / `reticle.status_changed`（D68 补充）

### 光罩事件 payload（D72，aggregate_type=reticle，aggregate_id=reticle_id）
公共字段（每个事件都带）：`reticle_id`、`reticle_code`、`tenant_id`、`occurred_at`（UTC Z）、`actor`（username，或 eap/system）、`source`（manual/eap/simulator/system）。数值一律是十进制字符串。

| 事件 | 额外字段 |
|---|---|
| reticle.mounted | equipment_id, equipment_code, shots_at_mount |
| reticle.unmounted | equipment_id, equipment_code, shots_at_unmount, trigger（manual/hold/incident） |
| reticle.life_reached | shot_count, max_shots |
| reticle.held | from_status, hold_reason, previous_hold_reason（升级时才有，否则为 null）, status_before_hold, reason |
| reticle.released | hold_reason, to_status, reason |
| reticle.restored | from_status, to_status, reason, inspection_required |
| reticle.life_reset | shot_count_before, reason |
| reticle.incident_recorded | incident_id, incident_type, alarm_source, external_event_id（可为 null）, caused_hold（bool） |
| reticle.inspected | inspection_id, result（pass）, to_status |
| reticle.inspection_failed | inspection_id, result（fail）, disposition, to_status |
| reticle.scrapped | from_status, reason, equipment_id（在用时才有，否则为 null）, shots_at_unmount（在用时才有，否则为 null） |
| reticle.status_changed | from_status, to_status, action（clean_start/clean_complete/repair_complete/inspect_start） |

### 人员资质事件（D74，aggregate_type=operator_qual，aggregate_id=qual_id，outbox 前记 audit_log）
公共字段：`qual_id`、`tenant_id`、`username`、`operation_id`、`operation_code`、`equipment_type_id`（可为 null）、`occurred_at`（UTC Z）、`actor`（username 或 system）。

| 事件 | 额外字段 |
|---|---|
| operator_qual.granted | certified_on, expires_on, reason_id, comment（可空） |
| operator_qual.renewed | expires_on_before, expires_on, reason_id, reason_code, comment, approved_by（均必填，D74 补充 Q6-2） |
| operator_qual.changed | changes（字段→[旧,新]）, reason_id, comment（可空） |
| operator_qual.deactivated | reason_id, reason_code, comment（必填，D74 补充 Q6-2） |
| operator_qual.expired | expires_on（定时扫描发出，按 qual_id+expires_on 去重） |

P3-B5 CT/Move 报表（D73）只读，不发事件。

- `lot.marking_mismatched`（D78）：OCR 读回内容与计划不一致。payload 含 marking_id、print_id、expected_code、read_code。
- `lot.marked`（D78）：一次打印完成。payload：marking_id、print_id、seq、trace_code、source、external_event_id、equipment_id、reason_id（seq=1 时为 null，键始终存在）。
- `lot.marking_inspected`（D78）：一次检验完成。payload：marking_id、print_id、inspection_id、result（pass/fail）、source、external_event_id。
- `lot.marking_voided`（D78）：打标记录作废。payload：marking_id、reason_id、comment。
