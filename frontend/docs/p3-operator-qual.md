# P3 人员资质：前端说明

依据：decisions.md D74（P3-B6 契约定稿）、D62（第 5 到 8 条）、D64，以及后端已有的 `operator_qual` 实体和检查项 `operator_qualified`。

## 已定稿
- **权限：** 读用 `mes.exec:read`，写用 `mes.exec:write`（以 specs 注册为准，不新增权限名）。
- **预警天数：** 单一来源是 `warn_days`，必须是 1–365 的整数，设置值缺失或非法（含 0）都按 30。定时提醒 `qual_expiry_notice` 也读同一值。后端放在 `operator_qual` 实体元数据的 `warn_days` 里，列表页着色从元数据读，读不到用 30 天（`warnDaysOf`）。汇总接口返回同一个值；进站检查如果 `data.warn_days` 有值也会用上。
- **阻断：** `operator_qualified` 不通过时，后端返回 409 `check_blocked`，`overridable=false`，主管也不能放行。界面不显示放行表单，并用三语提示“不能进站，且不可放行”。
- **通用放行逻辑（复用并扩展 `CheckPanel`）：** 前端只看响应里每条结果的 `overridable`。只要有一条是不能放行的阻断，就不显示放行表单，改为提示“存在不可放行的检查项”。`overridable=true` 时（比如以后的光罩待检），有权限的人可以看到放行表单。多个原因时，后端规定 `reasons[]` 里只要有一条不能放行，整体就是 `overridable=false`。文案优先用本地化说明；没有本地化时，有多条 `reasons[]` 就全部列出，否则取 `reason`，再不行就用 `message`。
- **资质匹配：** “工序+设备类型”的资质优先于“只按工序”的资质（`pickQual`，只用于界面提示，以后端判定为准）。`expires_on` 当天仍然有效，后端按站点时区的“今天”判断。同时命中两种资质时，后端 `data.expires` 取“工序+设备类型”那条，与 `pickQual` 一致。
- **即将到期人员汇总：** 接口是 `GET /api/v1/mes/exec/operator-qual/expiring?days=`，权限 `mes.exec:read`。前端默认不传 `days`，后端会取设置值（默认 30）。`days` 传了就必须是 1–365 的整数，否则后端返回 422 `value_error`（`ctx` 带 `min=1`、`max=365`），不会静默按 30；只有设置值缺失或非法才按 30。页面组件 key 是 `mes-page:qual-expiring`，菜单 key 是 `mes-qual-expiring`。返回形状照下面的前端稿定稿。接口只返回 `is_active=true` 且 `days_left` 在 [0, days] 内的资质（`days_left` 按站点时区今天计算，当天为 0）；停用的资质和 `expires_on` 为空（永久）的资质都不返回。按 `days_left` 升序排，相同时再按 `username` 排；前端保持后端顺序不重排，只兜底过滤 `days_left < 0` 的行。接口返回 404 时用示例数据（不含已过期的行），并显示“示例数据”标签。
- **资质履历：** 接口是 `GET /api/v1/mes/exec/operator-qual/{qual_id}/history`，权限 `mes.exec:read`（无权限 403 优先于 404）。返回 `{rows[{id, action, before, after, reason, username, at}]}`，按 `at` 倒序，支持 `limit`（默认 50，最大 200）和 `offset`。`action` 取值：granted/renewed/changed/deactivated/reactivated/expired；`before`/`after` 是变更字段快照，`at` 是 UTC。旧数据不补履历。通用 CRUD 写入时可在请求体顶层带可选的 `reason`（≤300 字），不要求 Idempotency-Key。考核记录作废，不做。
- **删除：** 有履历的资质删除返回 409 `referenced`（`detail.tables[]` 列出有记录的表），只能停用（`is_active=false`），同 D72。前端遇到该错误提示改用停用。

汇总接口的返回形状（已定稿）：

```json
{ "warn_days": 30, "timezone": "Asia/Taipei",
  "rows": [{ "qual_id": "uuid", "username": "op1", "operation": "WB",
             "equipment_type": null, "expires_on": "2026-11-01", "days_left": 0 }] }
```

## 待定
1. 后端菜单 key `mes-qual-expiring` 还没落地，后端会跟菜单键导出一起加；在此之前保留在 `PENDING_MENU_KEYS` 里。
2. 工艺专家/kai mi 待定（D74 Q6-1～Q6-3）：过期是否自动停用（暂定不自动，只发 expired 事件并写履历）；停用/延期是否必须填 `reason`（暂定可选）；是否单独设“资质授予”权限（暂定沿用 `mes.exec:write`）。
