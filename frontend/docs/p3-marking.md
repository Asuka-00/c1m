# P3-F4 打标模板与打标作业页面（前端）

依据：architect/design/p3-tasks.md（P3-B1~B3、P3-F4）、decisions.md D70~D78（含 D78 补充一~三）、设备集成预审 eap/p3 `e462675` docs/p3-e2-marking-prereview.md。后端 B1~B3 未就绪，前端默认走 mock（`VITE_MARKING_MOCK=0` 切真实接口，写法同光罩）。

## 页面与文件
| 内容 | 文件 |
|---|---|
| 接口层 + mock + 规则 | `src/lib/api/mes/marking.ts`（测试 `marking.test.ts`） |
| 打标模板页（组件 key `mes-page:marking-template`） | `src/features/mes/marking/template-page.tsx` |
| 打标作业页（组件 key `mes-page:marking`） | `src/features/mes/marking/job-page.tsx` |
| 错误文案、幂等键、权限码、追溯码规则 hook | `src/features/mes/marking/marking-rules.ts` |
| 页面测试 | `src/features/mes/marking/marking-pages.test.tsx` |
| 追溯页 `kind=trace_code` | `src/features/mes/execution/trace.tsx`、`lib/api/mes/execution.ts` |
| 出站 `check_blocked`（`marking_inspection`）文案 | `src/features/mes/execution/check-message.ts` |
| 菜单 key（后端未导出） | `PENDING_MENU_KEYS`：`mes-marking`、`mes-marking-template` |

## 已按约定实现
- 模板：draft→approved→retired；已批准只读（409 `template_readonly`）；新版本批准后旧版自动 retired；起草人不能自批：前端按 `/auth/me` 的 username 与 `created_by` 比对禁用按钮并提示，mock 返回 422 `self_approval`（D79）。
- 版本对比：同「产品+客户」其他版本，逐字段（日期码取值、含 bin）逐行对比。
- 作业：预览（`GET /mes/marking/preview?lot_id=`）→ 建主记录（`POST /mes/marking`）+ 首打（`POST /mes/marking/{id}/prints`）→ 检验（`POST /mes/marking/{id}/inspect`）→ 不合格重打（`prints`，必填 `reason_id`+`comment`≤300，reason_type `marking_reprint`）→ 作废（`POST /mes/marking/{id}/void`，必填 `reason_id`（`marking_void`）+`comment`，二次确认，不可恢复）。
- D78：每次打印一条 `prints[]`（seq 后端分配，前端不传）；检验 `inspections[]` 带 `print_id`/`seq`，按打印分组显示；OCR 读回与系统号不一致强制 fail，显示 expected/read 差异；`reprint_count` 只读；拦出站只看 `latest_inspection_status`（重打后回 pending）。
- 打印 / 重打 / 检验 / 作废都带 Idempotency-Key：同一请求体重试沿用同一个 key（重放返回原记录，不加行），改了内容换新 key；缺 key 422 `missing`（loc `["header","Idempotency-Key"]`）、同 key 不同内容 422 `idempotency_key_reused`，都有文案。
- 作废或批次已报废：打印 / 检验 / 重打 / 作废按钮禁用；mock 409 `invalid_transition`。作废按钮由 `mes.marking:void` 控制，与 `mes.marking:exec` 分开。
- 追溯码：以 `GET /mes/marking/config` 为准（取不到用 32、`^[A-Z0-9-]+$`），违反几条显示几条（对应后端逐条 422 `value_error`，`ctx.reason`=max_length/pattern）。
- D78 补充四/五：config 的 pattern 直接 `new RegExp(pattern)`、不加 flag、全串匹配，长度单独按 `trace_code_max_length`；纯空白只按 `/^[ \t\r\n\u3000]*$/` 判断（不用 trim），命中只提示「必填」（对应 422 `missing`）；其他值原样提交、不去空格、不转大写，U+FEFF、`\x1f` 等按格式错误。
- `trace_code_mismatch`（ctx.expected/actual）、`check_blocked`+`ctx.check=marking_inspection`（不可强制放行）三语文案。
- D77：作业页打标日期范围用 `rangeParam`（`marked_at_from` 站点当天 0 点、`marked_at_to` 站点次日 0 点）；D75：日期码按站点日期、默认日期 `siteToday()`；打标表没有定点字段（D79 去掉 qty），超位 422 `value_error`+`ctx.max_places` 仍保留通用文案。

## D79 落地（2026-10-15）
- 模板 `lines` 为字符串数组，占位符 `{name}` 白名单 `trace_code`、`date_code`、`lot_id`、`product_code`、`customer_code`；前端编辑时预校验（不通过禁用保存），后端 422 `value_error` `ctx.reason=unknown_placeholder` 有文案。列表显示只读 `product_name` / `customer_name`。
- 新版本：`POST /mes/marking-template/{id}/versions`（复制最新版本为草稿，版本号后端递增），已有草稿 409 `draft_exists`。
- 自批：422 `value_error` `ctx.reason=self_approval`（前端仍禁用按钮）；`template_readonly`、`draft_exists`、`already_marked` 为 409。
- 作业：`POST /mes/marking` 只建主记录（发号）；所有打印（含首打）走 `POST /mes/marking/{id}/prints`，seq 后端分配，seq>1 必填原因。
- 检验：填 pass 但读回不一致强制 fail，响应 `{record, result, expected_code, read_code, result_overridden}`；页面提示「你填的是 pass，系统已记为 fail」，履历里标「系统改判」。
- 作废后可同批次重新首打（新主记录、新号、seq 从 1）；同一批次最多一条未作废主记录，否则 409 `already_marked`。
- 追溯 `kind=trace_code` 结果 `{marking_id, lot_id, trace_code, voided, prints[{print_id, seq, marked_at, latest_inspection_result}]}`；默认不含已作废，页面开关「含已作废」传 `include_voided=true`。
- 筛选 `marked_at_from` / `marked_at_to`（D77 半开区间）；去掉 qty。
- 权限：`mes.marking:read`（模板+作业读）、`mes.marking_template:write`（模板编辑 / 新建版本）、`mes.marking_template:approve`（审批 / 退役）、`mes.marking:exec`（打印、检验）、`mes.marking:void`（作废）。

## 待确认问题
1. **Q7（等工艺专家）**：trace_code 长度和字符集；前端读 `/mes/marking/config`，暂按 ≤32、`^[A-Z0-9-]+$`。

已定（D78/D79），划掉：
- ~~模板 `lines` 形状~~（D79-1：字符串数组 + `{name}` 白名单）
- ~~自批错误码~~（D79-2：422 `value_error` `ctx.reason=self_approval`）
- ~~改已批准 / 已有草稿的错误码~~（D79-2：409 `template_readonly` / `draft_exists`）
- ~~新建版本方式~~（D79-1：`POST .../{id}/versions`）
- ~~模板显示名~~（D79-1：只读 `product_name` / `customer_name`）
- ~~模板 `created_by`~~（D79-1：返回）
- ~~重打请求形状~~（D79-3：`POST /mes/marking/{id}/prints`）
- ~~首打已存在的错误码~~（D79-5：409 `already_marked`）
- ~~预览是否返回原号~~（已按未作废主记录返回原号和内容）
- ~~记录列表参数名~~（D79-6：`marked_at_from` / `marked_at_to`）
- ~~pass 但读回不一致~~（D79-4：强制 fail，`result_overridden=true`）
- ~~打标数量 qty~~（D79-6：没有）
- ~~作废后能否重新首打、追溯是否排除已作废~~（D79-5：可以；默认排除，`include_voided=true` 才含）
- ~~`kind=trace_code` 结果形状~~（D79-6）
- ~~菜单 key 导出~~（D79-7：B2 登记并导出；导出前前端仍放在 `PENDING_MENU_KEYS`）
- ~~模板读与作业读是否分开~~（D79-7：`mes.marking:read` 覆盖两者）
- ~~预审 Q1~Q6~~（D78）

## D79 补充二（已落实）

1. 同一次打印可多次检验，以最新一次为准；mock 已去掉「已检验过 409」。批次离开打标工步后检验返回 409 `invalid_transition`（mock 用 `markingMockLeaveStep` 模拟）。
2. 长度一律按码点 `[...s].length`（`MARKING_POLICY.lengthMode='codepoint'`）。
3. 读回码不校验格式，不一致强制记 fail；空值 / 纯空白 422 `missing`；超过 128 码点 422 `value_error`（`ctx.reason=max_length, max_length=128`），前端同口径预校验。
4. `/mes/marking/config` 的正则只接受正向字符类 `^[...]+$`，不合规时前端不做格式预校验（以后端为准）。
5. 重打不要求上次检验是 fail。
6. E7：`marked_at` 为首打时间（未首打为 null），之后不变；新增只读 `last_printed_at`；`marked_at_from/_to` 按首打时间筛选（D77 半开）；列表显示「首打时间」「最近打印」两列。

待定问题仍只剩 Q7（出站检验失败未处理的错误码）。
