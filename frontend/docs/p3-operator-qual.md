# P3 人员资质：前端说明

依据：D62（第 5 到 8 条）、D64，以及后端已有的 `operator_qual` 实体和检查项 `operator_qualified`。

## 已定稿
- **预警天数：** 后端放在 `operator_qual` 实体元数据的 `warn_days` 里，列表页着色从元数据读，读不到用 30 天（`warnDaysOf`）。汇总接口返回同一个值；进站检查如果 `data.warn_days` 有值也会用上。
- **阻断：** `operator_qualified` 不通过时，后端返回 409 `check_blocked`，`overridable=false`，主管也不能放行。界面不显示放行表单，并用三语提示“不能进站，且不可放行”。
- **通用放行逻辑（复用并扩展 `CheckPanel`）：** 前端只看响应里每条结果的 `overridable`。只要有一条是不能放行的阻断，就不显示放行表单，改为提示“存在不可放行的检查项”。`overridable=true` 时（比如以后的光罩待检），有权限的人可以看到放行表单。多个原因时，后端规定 `reasons[]` 里只要有一条不能放行，整体就是 `overridable=false`。文案优先用本地化说明；没有本地化时，有多条 `reasons[]` 就全部列出，否则取 `reason`，再不行就用 `message`。
- **资质匹配：** “工序+设备类型”的资质优先于“只按工序”的资质（`pickQual`，只用于界面提示，以后端判定为准）。`expires_on` 当天仍然有效，后端按站点时区判断。
- **即将到期人员汇总：** 接口是 `GET /api/v1/mes/exec/operator-qual/expiring?days=`，权限沿用 `operator_qual` 的读权限。前端默认不传 `days`，后端会取设置值（默认 30）。页面组件 key 是 `mes-page:qual-expiring`，菜单 key 是 `mes-qual-expiring`。返回形状照下面的前端稿定稿。接口只返回未过期的资质（`days_left >= 0`，当天为 0），按 `days_left` 升序排，相同时再按 `username` 排，前端也按同样规则兜底排序；页面不处理已过期的情况。接口返回 404 时用示例数据（不含已过期的行），并显示“示例数据”标签。
- **资质履历：** 属于 P3-B6，等后端做完再接。考核记录作废，不做。

汇总接口的返回形状（已定稿）：

```json
{ "warn_days": 30, "timezone": "Asia/Taipei",
  "rows": [{ "qual_id": "uuid", "username": "op1", "operation": "WB",
             "equipment_type": null, "expires_on": "2026-11-01", "days_left": 0 }] }
```

## 待定
1. 后端菜单 key `mes-qual-expiring` 还没落地，后端会跟菜单键导出一起加；在此之前保留在 `PENDING_MENU_KEYS` 里。
