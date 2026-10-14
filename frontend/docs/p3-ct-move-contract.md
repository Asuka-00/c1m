# P3 CT / Move 报表：前端假设的接口（草案，待后端 / 架构确认）

依据：`architect/design/gap-list.md` D 组、`bom.md` P3 列表只写了“Cycle Time 和 Move 报表”，没有细节。下面是前端按现有报表（OEE / 良率）的风格做的假设。类型定义在 `src/lib/api/mes/ct-move.ts`，接口返回 404 时页面会显示示例数据（`ctMoveMock`），并打上“示例数据”标签。

## 接口
`GET /api/v1/mes/exec/reports/ct-move`，权限假设 `mes.exec:read`。

| 参数 | 必填 | 说明 |
|---|---|---|
| `date_from` / `date_to` | 是 | `YYYY-MM-DD`，按租户时区的自然日，含两端（D54-4 的租户时区） |
| `operation_id` | 否 | 只看一个工序 |
| `product_id` | 否 | 只看一个产品 |

响应（小数按 D50 用十进制字符串，时间为 UTC Z）：
```json
{
  "date_from": "2026-10-01",
  "date_to": "2026-10-14",
  "timezone": "Asia/Taipei",
  "trend": [
    { "day": "2026-10-01", "moves": 42, "move_qty": "1050", "ct_avg_hours": "3.75" }
  ],
  "by_operation": [
    {
      "operation_id": "uuid", "operation": "WB", "operation_name": "Wire bond",
      "moves": 120, "move_qty": "3000",
      "ct_avg_hours": "3.50", "ct_p50_hours": "3.20", "ct_p90_hours": "5.40",
      "wip_lots": 5
    }
  ],
  "total": { "moves": 588, "move_qty": "14700", "ct_avg_hours": "4.25" }
}
```

## 口径假设（需要确认）
1. **Move**：一次 Track Out 算 1 个 move，按批次计数；`move_qty` 是出站数量合计。分批 / 合批 / 跳站 / 返工是否计入待定。
2. **CT**：工序 CT = 本工序 Move In（无 Move In 时用上一工序 Track Out）到本工序 Track Out 的时长，单位小时；按出站日期归日。Hold 时间是否扣除待定。
3. **分桶**：按租户时区自然日；跨度上限假设 92 天，超出 422。
4. **P50 / P90**：按批次 CT 计算的分位数；数据不足为 null。
5. **wip_lots**：查询区间最后一天结束时该工序的在制批数。
6. **菜单**：组件 key 假设 `mes-page:ct-move-report`，菜单 key `mes-ct-move-report`，放在“报表”组。
