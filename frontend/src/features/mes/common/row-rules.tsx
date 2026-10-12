/** 实体专用的单元格渲染与行编辑 / 删除规则。 */
import { t } from '@/i18n'
import type { MesRow } from '@/lib/api/mes/common'
import { ToolLife } from '@/features/mes/execution/exec-actions'
import { WoProgress } from '@/features/mes/planning/wo-actions'
import { DowntimeEnd, DueCell } from './due-cells'
import { RefLink } from './ref-link'

/** 实体专用单元格渲染器：实体 -> 字段 -> 单元格。 */
export const CELLS: Record<
  string,
  Record<string, (r: MesRow) => React.ReactNode>
> = {
  work_order: {
    started_qty: (r) => <WoProgress row={r} />,
    // 交期：未完结且已过交期标“逾期”，3 天内到期标黄
    due_date: (r) => (
      <DueCell
        date={r.due_date as string | null}
        done={WO_DONE.includes(String(r.wo_status))}
        warnDays={3}
        overLabel={t('mes.due.overdue')}
      />
    ),
  },
  // 物料批：已过有效期标“过期”，7 天内到期标“临期”
  material_lot: {
    expiry_date: (r) => (
      <DueCell
        date={r.expiry_date as string | null}
        warnDays={7}
        overLabel={t('mes.due.expired')}
        warnLabel={t('mes.due.expiring')}
      />
    ),
  },
  // 审计日志：记录跳转到被修改对象
  audit_log: {
    record_code: (r) =>
      r.record_id ? (
        <RefLink
          target={String(r.entity_type)}
          id={String(r.record_id)}
          label={String(r.record_code ?? r.record_id)}
        />
      ) : (
        String(r.record_code ?? '—')
      ),
  },
  // 停机：显示持续时长；未结束的停机醒目标识
  downtime: {
    end_at: (r) => <DowntimeEnd row={r} />,
  },
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

/** 已完结的工单状态（不再计算逾期）。 */
const WO_DONE = ['completed', 'closed', 'cancelled']
