# P3 CT / Move 报表接口契约

依据：decisions.md D62、D63，以及架构和后端后来的补充（D64 前后的群内答复）。类型定义在 `src/lib/api/mes/ct-move.ts`。接口没上线（返回 404）时，页面用 `ctMoveMock` 示例数据，并显示“示例数据”标签。

## 已定稿
- **接口：** `GET /api/v1/mes/exec/reports/ct-move`，权限 `mes.exec:read`。组件 key 是 `mes-page:ct-move-report`，菜单 key 是 `mes-ct-move-report`。
- **参数：** `date_from`、`date_to`（`YYYY-MM-DD`，含两端），可选 `operation_id`、`product_id`。
- **日期跨度：** 最多 92 天，超出时后端返回 422 `date_range_too_large`。前端提交前先校验并给出三语提示，后端返回的这个错误码也做了三语本地化。
- **时区：** 用站点时区，由后端分桶。前端不写死时区，页面显示响应里的 `timezone`。规则同 D54 导出。
- **Move：** 一次出站算 1 个 move。`moves` 是批次 move 数，`move_qty` 是晶圆 move 数，也就是出站片数。拆批、合批、跳站都不算 move。
- **返工：** 返工出站计入 `rework_moves`、`rework_move_qty`，不计入 `moves`、`move_qty`，也不算产出效率。
- **CT：** 从上一工序出站算起（首工序从开批算起），到本工序出站为止，单位是小时。按出站日期归到某一天，不扣 Hold 时间。按工序给 `ct_avg_hours`、`ct_p50_hours`、`ct_p90_hours`。只做工序 CT，批次 CT 不进 P3。
- **Hold：** `hold_hours` 单独一个字段，单位是小时，十进制字符串，无数据时为 null。
- **子批和合批：** 子批 CT 的起点继承母批上一次出站的时间；合批后取各源批中最早的时间。这两条由后端计算，前端不用处理。
- **在制：** `wip_lots` 是期末在制批数。
- **空数据：** 计数字段（`moves`、`move_qty`、`rework_*`、`wip_lots`）返回 0，时长字段（`ct_*`、`hold_hours`）返回 null，`total` 同样如此。`trend` 把每一天都列出来，没数据的日子计数为 0、CT 为 null。图表里 null 的点不连线，提示框显示“—”。前端会把后端缺省的字段补成 0 或 null（`normalizeReport`）。

```json
{
  "date_from": "2026-10-01", "date_to": "2026-10-14", "timezone": "Asia/Taipei",
  "trend": [{ "day": "2026-10-01", "moves": 42, "move_qty": "1050",
              "rework_moves": 1, "rework_move_qty": "25",
              "ct_avg_hours": "3.75", "hold_hours": "1.50" }],
  "by_operation": [{ "operation_id": "uuid", "operation": "WB", "operation_name": "Wire bond",
              "moves": 120, "move_qty": "3000", "rework_moves": 2, "rework_move_qty": "50",
              "ct_avg_hours": "3.50", "ct_p50_hours": "3.20", "ct_p90_hours": "5.40",
              "hold_hours": "0.40", "wip_lots": 5 }],
  "total": { "moves": 588, "move_qty": "14700", "rework_moves": 9, "rework_move_qty": "225",
             "ct_avg_hours": "4.25", "hold_hours": "8.50" }
}
```

## 待定
1. `hold_hours` 在 trend 和 by_operation 里是合计还是平均：前端只当数值显示，表头写的是“Hold 时长（小时）”。
2. `p3-tasks.md` 里写的两个接口（`/mes/report/move`、`/mes/report/cycle-time`）、权限 `mes.report:read` 和批次 CT 是否已同步改掉，要请架构确认文档已更新。前端按上面的定稿实现。
3. 后端菜单 key `mes-ct-move-report` 还没落地，目前列在 `PENDING_MENU_KEYS` 里。
4. 工艺专家后续如果调整口径，可能还要改（D62 里有说明）。
