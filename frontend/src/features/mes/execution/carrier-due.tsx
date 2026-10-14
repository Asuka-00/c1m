/** 载具清洗 / 使用状态徽标。 */
import { t } from '@/i18n'
import type { CarrierRow } from '@/lib/api/mes/execution'
import { compareDecimal, decimalText } from '@/lib/decimal'
import { Badge } from '@/components/ui/badge'

const VARIANT = {
  ok: 'secondary',
  warn: 'outline',
  overdue: 'destructive',
} as const

/**
 * 显示载具的到期状态与使用次数。
 *
 * @param row - 载具总览行
 */
export function CarrierDue({ row }: { row: CarrierRow }) {
  return (
    <span className='flex items-center gap-2'>
      <Badge variant={VARIANT[row.due_state]} data-state={row.due_state}>
        {t(`mes.carrier.due.${row.due_state}`)}
      </Badge>
      <span className='text-xs text-muted-foreground tabular-nums'>
        {decimalText(row.use_count)}
        {row.max_uses != null && compareDecimal(row.max_uses, 0) === 1
          ? ` / ${decimalText(row.max_uses)}`
          : ''}
      </span>
    </span>
  )
}
