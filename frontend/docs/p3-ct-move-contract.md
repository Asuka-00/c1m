# P3 CT / Move 报表接口契约

依据：decisions.md D73（P3-B5 契约定稿），以及 D62、D63、D64。类型定义在 `src/lib/api/mes/ct-move.ts`。接口没上线（返回 404）时，页面用 `ctMoveMock` 示例数据，并显示“示例数据”标签。

## 已定稿
- **接口：** `GET /api/v1/mes/exec/reports/ct-move`，权限 `mes.exec:read`，只读。无权限返回 403；`operation_id`/`product_id` 不存在或不属于本租户返回 404。旧接口 `/mes/report/move`、`/mes/report/cycle-time` 和权限 `mes.report:read` 作废，前端不得再用。组件 key 是 `mes-page:ct-move-report`，菜单 key 是 `mes-ct-move-report`。
- **参数：** `date_from`、`date_to` 必填（`YYYY-MM-DD`，含两端），可选 `operation_id`、`product_id`（uuid）。日期格式错误或 `date_from > date_to` 统一返回 422 `value_error`，不另起错误码；未知参数后端忽略，不报 `unknown_field`。
- **日期跨度：** 最多 92 天，超出时后端返回 422 `date_range_too_large`（`ctx.max_days=92`）。前端提交前先校验并给出三语提示，后端返回的这个错误码也做了三语本地化。
- **时区：** 用站点时区，由后端分桶。前端不写死时区，页面显示响应里的 `timezone`（IANA 名）。规则同 D54 导出。`day` 是站点日期字符串，响应里的时间点（如有）仍是 UTC Z。
- **Move：** 一次出站算 1 个 move。`moves` 是批次 move 数，`move_qty` 是晶圆 move 数，也就是出站片数。两者都是 JSON 整数。拆批、合批、跳站都不算 move。
- **返工：** 返工出站计入 `rework_moves`、`rework_move_qty`，不计入 `moves`、`move_qty`，也不算产出效率。`rework_move_qty` 同样是 JSON 整数。撤销的转换不计入（D60）。
- **CT：** 从上一工序出站算起（首工序从开批算起），到本工序出站为止，单位是小时。按出站日期归到某一天，不扣 Hold 时间。CT 只统计非返工出站。`ct_avg_hours` 在 `trend`、`by_operation`、`total` 里都有；`ct_p50_hours`、`ct_p90_hours` 只在 `by_operation` 里给，`trend` 和 `total` 不带，前端不要补这两个字段。分位数用线性插值（同 PostgreSQL `percentile_cont`）。只做工序 CT，批次 CT 不进 P3。
- **Hold：** `hold_hours` 是平均 Hold 时长：在每日趋势、按工序表和 total 里都按出站批次取平均（口径同 `ct_avg_hours`），单位是小时，十进制字符串，无数据时为 null。页面标签是“平均 Hold 时长（小时）”。
- **子批和合批：** 子批 CT 的起点继承母批上一次出站的时间；合批后取各源批中最早的时间。这两条由后端计算，前端不用处理。
- **在制：** `wip_lots` 是 `date_to` 当天站点时区日末的在制批数，只在 `by_operation` 里给。
- **数值格式：** 时长字段（`ct_*`、`hold_hours`）是十进制字符串，固定 2 位小数（ROUND_HALF_UP）。计数字段（`moves`、`move_qty`、`rework_moves`、`rework_move_qty`、`wip_lots`）是 JSON 整数；片数不是定点小数，D50/D72 的“定点数输出字符串”不适用。`normalizeReport` 仍兼容字符串输入。
- **排序：** `by_operation` 只列有出站或有在制的工序，按工艺路线顺序、再按 operation 编码排序。
- **空数据：** 计数字段（`moves`、`move_qty`、`rework_*`、`wip_lots`）返回 0，时长字段（`ct_*`、`hold_hours`）返回 null，`total` 同样如此。`trend` 把每一天都列出来，没数据的日子计数为 0、CT 为 null。图表里 null 的点不连线，提示框显示“—”。前端会把后端缺省的字段补成 0 或 null（`normalizeReport`）。

```json
{
  "date_from": "2026-10-01", "date_to": "2026-10-14", "timezone": "Asia/Taipei",
  "trend": [{ "day": "2026-10-01", "moves": 42, "move_qty": 1050,
              "rework_moves": 1, "rework_move_qty": 25,
              "ct_avg_hours": "3.75", "hold_hours": "1.50" }],
  "by_operation": [{ "operation_id": "uuid", "operation": "WB", "operation_name": "Wire bond",
              "moves": 120, "move_qty": 3000, "rework_moves": 2, "rework_move_qty": 50,
              "ct_avg_hours": "3.50", "ct_p50_hours": "3.20", "ct_p90_hours": "5.40",
              "hold_hours": "0.40", "wip_lots": 5 }],
  "total": { "moves": 588, "move_qty": 14700, "rework_moves": 9, "rework_move_qty": 225,
             "ct_avg_hours": "4.25", "hold_hours": "8.50" }
}
```

## 待定
1. 后端菜单 key `mes-ct-move-report` 还没落地，后端会跟菜单键导出一起加；在此之前保留在 `PENDING_MENU_KEYS` 里。
2. 工艺专家待定口径（D73 T5-1～T5-3）：返工出站的判定、`wip_lots` 是否含 Hold 中的批次、跨工序 Hold 的 `hold_hours` 归属。暂定为：返工路线/工步上出站才算返工；`wip_lots` 含 Hold；Hold 时长归到其所在工序的出站。以后只改计算口径，接口不变。
