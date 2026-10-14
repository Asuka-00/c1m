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
- 模板：draft→approved→retired；已批准只读（mock 409 `template_readonly`）；新版本批准后旧版自动 retired；起草人不能自批：前端按 `/auth/me` 的 username 与 `created_by` 比对禁用按钮并提示，mock 返回 409 `self_approval`。
- 版本对比：同「产品+客户」其他版本，逐字段（日期码取值、含 bin）逐行对比。
- 作业：预览（`GET /mes/marking/preview?lot_id=`）→ 打印（`POST /mes/marking`）→ 检验（`POST /mes/marking/{id}/inspect`）→ 不合格重打（同接口带 `record_id`，必填 `reason_id`+`comment`≤300，reason_type `marking_reprint`）→ 作废（`POST /mes/marking/{id}/void`，必填 `reason_id`（`marking_void`）+`comment`，二次确认，不可恢复）。
- D78：每次打印一条 `prints[]`（seq 后端分配，前端不传）；检验 `inspections[]` 带 `print_id`/`seq`，按打印分组显示；OCR 读回与系统号不一致强制 fail，显示 expected/read 差异；`reprint_count` 只读；拦出站只看 `latest_inspection_status`（重打后回 pending）。
- 打印 / 重打 / 检验 / 作废都带 Idempotency-Key：同一请求体重试沿用同一个 key（重放返回原记录，不加行），改了内容换新 key；缺 key 422 `missing`（loc `["header","Idempotency-Key"]`）、同 key 不同内容 422 `idempotency_key_reused`，都有文案。
- 作废或批次已报废：打印 / 检验 / 重打 / 作废按钮禁用；mock 409 `invalid_transition`。作废按钮由 `mes.marking:void` 控制，与 `mes.marking:exec` 分开。
- 追溯码：以 `GET /mes/marking/config` 为准（取不到用 32、`^[A-Z0-9-]+$`），违反几条显示几条（对应后端逐条 422 `value_error`，`ctx.reason`=max_length/pattern）。
- `trace_code_mismatch`（ctx.expected/actual）、`check_blocked`+`ctx.check=marking_inspection`（不可强制放行）三语文案。
- D77：作业页打标日期范围用 `rangeParam`（`marked_at_from` 站点当天 0 点、`marked_at_to` 站点次日 0 点）；D75：日期码按站点日期、默认日期 `siteToday()`；D76：数量等定点字段用 `lib/decimal`，超位 422 `value_error`+`ctx.max_places` 有文案。

## 待确认问题（问架构师 / 后端）
1. **Q7（D78 唯一未定，等工艺专家）**：trace_code 长度和字符集；前端已读 config，不写死。
2. 模板 `lines` 的 JSON 形状：前端按「字符串数组 + 占位符 `{model}` `{yyww}` `{trace}` `{bin}`」做；后端是否用结构化行（字段类型 + 位置）？
3. 自批 409 的 code：mock 用 `self_approval`（参照 D74 `ctx.reason=self_approval`），后端是否同名？是 409 `{code}` 还是 409 `invalid_transition`+`ctx.reason`？
4. 改已批准版本 409 的 code：mock 用 `template_readonly`；同「产品+客户」已有草稿时再建 mock 用 409 `draft_exists`——是否允许多个草稿？
5. 新建版本的方式：前端用 `POST /mes/marking-template`（同 code、产品、客户）由后端递增 version；是否另有 `POST .../{id}/new-version`（复制）？
6. 模板列表是否返回 `product`/`customer` 显示名（前端兜底显示 id）；产品 / 客户在表单里应是引用选择，当前 mock 用文本输入。
7. 模板是否有 `created_by`/`created_at` 字段（自批判断需要），字段名是否如此。
8. 重打的请求形状：`POST /mes/marking` 带 `record_id`，还是单独 `POST /mes/marking/{id}/reprint`？字段名 `record_id` 待定。
9. 首打已存在时再调 `POST /mes/marking`：mock 409 `already_marked`，后端 code？
10. 预览接口在已打过标时是否返回原号和实际内容（mock 返回）。
11. 记录列表接口：`GET /mes/marking?lot_id=&marked_at_from=&marked_at_to=` 是否提供、参数名是否如此（作业页依赖）。
12. 检验请求体：`{result, read_code?, comment?}`；人工检验是否允许不填 `read_code`？`result=pass` 但 `read_code` 不一致时后端是强制 fail（前端如此假设）还是 422？
13. 打标数量 `qty`（预审提到，可选）是否存在；如存在是定点还是整数。
14. 作废后的记录：是否允许对同一批次重新首打（发新号）？追溯码查询是否排除已作废记录（mock 排除）？
15. `kind=trace_code` 追溯结果形状：前端假设 `{kind, target{id,code}, marking{…}, wafers[{wafer,slot}], backward, forward}`，请 B3 定。
16. 菜单：`mes-marking-template`、`mes-marking` 的 key、父分组、组件 key、权限码请后端导出到 menu_keys.json。
17. 是否需要 `mes.marking:read` 之外再区分「模板读」和「作业读」。

（预审 Q1~Q6 已由 D78 定稿：Q1 每次打印追加 `mes_marking_print`；Q2 不加 sub_unit_id；Q3 `trace_code_mismatch`，OCR 不一致记 fail、事件 `lot.marking_mismatched`；Q4 检验独立表；Q5 `check_blocked`/`marking_inspection`；Q6 手工接口必须带 Idempotency-Key。）
