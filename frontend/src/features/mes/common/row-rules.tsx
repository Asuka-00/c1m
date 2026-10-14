/** 实体专用的单元格渲染与行编辑 / 删除规则。 */
import { t } from '@/i18n'
import type { MesEntity, MesRow } from '@/lib/api/mes/common'
import { Badge } from '@/components/ui/badge'
import { ToolLife } from '@/features/mes/execution/exec-actions'
import { qualState, warnDaysOf } from '@/features/mes/execution/operator-qual'
import { WoProgress } from '@/features/mes/planning/wo-actions'
import { DowntimeEnd, DueCell, HeldAt } from './due-cells'
import { enumLabel } from './labels'
import { RefLink } from './ref-link'

/** 实体专用单元格渲染器：实体 -> 字段 -> 单元格。 */
export const CELLS: Record<
  string,
  Record<string, (r: MesRow, e?: MesEntity) => React.ReactNode>
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
  // 人员资质（D62/D64）：过期红色，元数据 warn_days（缺省 30）天内到期黄色，停用不预警
  operator_qual: {
    expires_on: (r, e) => (
      <DueCell
        date={r.expires_on as string | null}
        done={qualState(r) === 'inactive'}
        warnDays={warnDaysOf(e?.warn_days)}
        overLabel={t('mes.due.expired')}
        warnLabel={t('mes.due.expiring')}
      />
    ),
  },
  // 批次：批次号进入批次作业；Hold 中红色徽标
  lot: {
    code: (r) => <RefLink target='lot' id={r.id} label={String(r.code)} mono />,
    on_hold: (r) =>
      r.on_hold ? (
        <Badge variant='destructive'>Hold</Badge>
      ) : (
        <span className='text-muted-foreground'>—</span>
      ),
  },
  // Hold：生效中的显示已持续时长
  lot_hold: {
    held_at: (r) => <HeldAt row={r} />,
  },
  // 优先级：颜色色块
  lot_priority: {
    color: (r) =>
      r.color ? (
        <span className='inline-flex items-center gap-2'>
          <span
            className='size-3 rounded-sm border'
            style={{ background: String(r.color) }}
          />
          <code className='text-xs'>{String(r.color)}</code>
        </span>
      ) : (
        '—'
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
  // D58：E10 履历的触发方式与事件来源、报警记录的来源（缺失显示 —）
  e10_history: {
    trigger: (r) => enumCell('e10_history_trigger', r.trigger),
    source: (r) => enumCell('e10_source', r.source),
  },
  alarm_log: { source: (r) => enumCell('alarm_source', r.source) },
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

/** 枚举单元格：三语标签；空值显示「—」。 */
function enumCell(en: string, v: unknown) {
  if (v == null || v === '')
    return <span className='text-muted-foreground'>—</span>
  return <Badge variant='outline'>{enumLabel(en, String(v))}</Badge>
}
