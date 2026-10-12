/** 实体专用的单元格渲染与行编辑 / 删除规则。 */
import type { MesRow } from '@/lib/api/mes/common'
import { ToolLife } from '@/features/mes/execution/exec-actions'
import { WoProgress } from '@/features/mes/planning/wo-actions'

/** 实体专用单元格渲染器：实体 -> 字段 -> 单元格。 */
export const CELLS: Record<
  string,
  Record<string, (r: MesRow) => React.ReactNode>
> = {
  work_order: { started_qty: (r) => <WoProgress row={r} /> },
  tool: { usage_count: (r) => <ToolLife row={r} /> },
  // 量测数据：超规值以红色高亮
  dc_result: {
    value: (r) => (
      <span
        className={
          r.is_oos
            ? 'font-semibold text-destructive tabular-nums'
            : 'tabular-nums'
        }
      >
        {r.value == null ? '—' : String(r.value)}
      </span>
    ),
  },
}

/** 父实体 -> 子表是否锁定（只读）的判断（在后端校验之外隐藏新增 / 编辑 / 删除）。 */
export const CHILD_LOCKS: Record<string, (parent: MesRow) => boolean> = {
  receipt: (p) => p.receipt_status !== 'draft',
}

/** 实体专用的编辑 / 删除规则（在权限与版本锁定之上）。 */
export const ROW_RULES: Record<
  string,
  { edit?: (r: MesRow) => boolean; remove?: (r: MesRow) => boolean }
> = {
  work_order: {
    edit: (r) => !['closed', 'cancelled'].includes(String(r.wo_status)),
    remove: (r) => r.wo_status === 'draft',
  },
  // 入库单仅草稿可改 / 删（明细的锁定由后端校验）
  receipt: {
    edit: (r) => r.receipt_status === 'draft',
    remove: (r) => r.receipt_status === 'draft',
  },
}
