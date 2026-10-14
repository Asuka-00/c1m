# TODO-409 前端盘点（fe/p3）

范围：`qa/reports/d81-p1p2-gap-inventory.md` 中标 **G7** 的 17 个接口——状态 / 业务冲突从 422 改为 D81 第 6 步的 409。
盘点基于 fe/p3 `frontend/src`（2026-10-15），只读核对，不含代码改动。

## 已定口径

1. 409 一律用对象格式 `{"detail": {"code": ..., "message": ..., ...}}`，不再用 `[{loc, msg, type}]` 列表。
2. 旧列表格式（`422` + `loc` 末段为 `lot_status` / `on_hold` …）的前端兜底**暂不删**，等 QA 在 8012 验证 17 个接口都已返回 409 对象格式后再删。
3. work-order 的 `start`、`transition`、`undo-start` 和设备 `e10` 都在范围内。
4. `e10` 的冲突 code 等后端给出；给出前前端按通用 `mesCodeMessage`（未登记的 code 显示后端 message）处理。

## G7 接口与前端调用点

| # | 接口 | 前端 API | 错误展示 | 改 409 后 |
|---|---|---|---|---|
| 9 | POST `/mes/eqp/{eq_id}/e10` | `lib/api/mes/equipment.ts:67` | `eqp-board.tsx:447,525` → `mesErrorMessage` | 无需改分支；后端给 code 后在 `MES_ERROR_CODES` 登记 + 三语 |
| 20 | POST `/mes/exec/lots/{lot_id}/hold` | `execution.ts:908` | `mesErrorMessage` | 无需改 |
| 22 | POST `/mes/exec/holds/{hold_id}/release` | `execution.ts:912` | `mesErrorMessage` | 无需改（确认 already released 的 code） |
| 23 | POST `/mes/exec/lots/{lot_id}/split` | `execution.ts:721` | `mesErrorMessage` | 无需改 |
| 24 | POST `/mes/exec/lots/{lot_id}/merge` | `execution.ts:728` | `mesErrorMessage` | 无需改 |
| 26 | POST `/mes/exec/lots/{lot_id}/jump` | `execution.ts:902` | `mesErrorMessage` | 无需改 |
| 27 | POST `/mes/exec/lots/{lot_id}/adjust` | `execution.ts:886` | `mesErrorMessage` | 无需改 |
| 30 | POST `/mes/exec/lots/{lot_id}/priority` | `execution.ts:868` | `mesErrorMessage` | 无需改（已有 409 unchanged） |
| 31 | POST `/mes/exec/carriers/{carrier_id}/clean` | `execution.ts:684` | `mesErrorMessage` | 无需改 |
| 32 | POST `/mes/exec/lots/{lot_id}/sort` | `execution.ts:673` | `mesErrorMessage` | 无需改 |
| 33 | POST `/mes/exec/lots/{lot_id}/carrier` | `execution.ts:692` | `mesErrorMessage` | 无需改 |
| 34 | POST `/mes/exec/lots/{lot_id}/{stage}` | `execution.ts:744` | `use-stage-run.ts:30`（按 code 刷新）+ `mesErrorMessage` | 无需改；测试改状态码 |
| 35 | POST `/mes/exec/batch/{stage}` | `execution.ts:708` | `mesErrorMessage` | 无需改 |
| 50 | POST `/mes/work-order/{rid}/transition` | `planning.ts:71` | `mesErrorMessage` | 无需改 |
| 52 | POST `/mes/work-order/{rid}/start` | `planning.ts:82` | `start-errors.ts:47,74`（仅 422）→ 其余走 `mesErrorMessage` | 无需改；补一条 409 wo_status 测试 |
| 53 | POST `/mes/work-order/{rid}/undo-start` | `planning.ts:88` | `mesErrorMessage` | 无需改 |
| 61 | POST `/mes/receipt/{rid}/transition` | `warehouse.ts:19` | `mesErrorMessage` | 无需改 |

## 按 422 / 409 分支的代码

| 位置 | 现状 | 改 409 后 |
|---|---|---|
| `features/mes/common/required.ts:216-232` `mesCodeMessage` | 对象格式按 `detail.code` 取文案，**不看状态码** | 无需改 |
| `features/mes/common/required.ts:250-256` `mesErrorMessage` | 先走 `mesCodeMessage`；之后**只在 422** 解析列表格式 | 无需改（409 为对象格式，见口径 1） |
| `features/mes/execution/lot-console/use-stage-run.ts:30` | `on_hold` / `lot_status` / `lot_busy` 按 code 触发刷新 | 无需改 |
| `lib/api/client.ts:163-196` `errorMessage` | 字符串 detail 与状态无关；422 只用于查询参数与列表 | 无需改 |
| `lib/api/mes/execution.ts:928,941` | 已按 409 + `check_blocked` 判断 | 无需改 |
| `features/mes/planning/start-errors.ts:47,74` | 仅 422 解析批次行 / 顶部错误 | 无需改（wo 状态冲突落到通用文案） |

不在范围（其他接口，已是 409 或与 G7 无关）：`transform-plan.ts:247`、`bin-split-plan.ts:134`、`transform-undo.ts:92`、`bom-errors.ts`、`qual-rules.ts`、`qual.tsx`、`mount-dialog.tsx`、`lib/api/mes/map.ts:136`。

## 旧列表格式兜底

`required.ts:253-256` 之后的列表解析（`field('on_hold', 'on_hold: ...')`、`lot_status: cannot <stage> a <status> lot` 等）。
按口径 2 保留；8012 验证通过后删除该兜底及 `required.test.ts:133-180` 的「旧格式兜底」用例。

## mock

17 个接口在前端没有抛状态冲突的 mock（`execution.ts` / `planning.ts` / `warehouse.ts` / `equipment.ts` 均直连后端）。
`reticle.ts`、`marking.ts`、`ct-move.ts` 的 422 / 409 mock 属其他接口，不受影响。

## 断言状态码的测试

| 位置 | 接口 | 改 409 后 |
|---|---|---|
| `features/mes/common/required.test.ts:28,38,53,65,73`（对象格式 on_hold / lot_status） | #20–35 | `axErr(422, …)` 改 409；断言不变 |
| `features/mes/common/required.test.ts:133-180`（旧格式兜底） | #23 #24 #34 | 暂留，8012 验证后删 |
| `features/mes/execution/lot-console/use-stage-run.test.tsx:224-227` | #34 | 标题与 `axErr` 改 409 |
| `features/mes/execution/overall-overridable.test.tsx:53` | #34 | 已是 409，不改 |
| 新增 | #52 | start 返回 409 `wo_status` 时显示通用文案 |
| 新增 | #9 | 后端给出 e10 code 后补文案与测试 |

`required.test.ts:193,232`（422 `idempotency_key_reused`）属 D57 / D81，不在 TODO-409 内。

## 工作量

- 后端切 409 后：测试改状态码约 6 处 + 新增 #52 测试，约 0.5 小时（含五项检查）。
- e10：拿到 code 后登记 `MES_ERROR_CODES` + 三语 + 测试，约 0.5 小时。
- 8012 验证后删旧格式兜底与对应测试：约 0.5 小时。
- 业务分支代码：不需要改。

## 待确认

- 后端：17 个接口的 409 detail 均为对象格式且 code 稳定（lot_status、on_hold、wo_status、already_released 等的最终 code 名）。
- 后端：e10 的冲突 code。
- QA：8012 验证完成时间（决定何时删旧格式兜底）。
