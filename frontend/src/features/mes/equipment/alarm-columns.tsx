/** 报警履历的状态联动列（baf7b55：`state_changed` / `state_skip_reason`）。 */
import { t } from '@/i18n'
import type { MesRow } from '@/lib/api/mes/common'
import { Badge } from '@/components/ui/badge'
import { alarmStateOf, skipReasonText } from './alarm-state'

const dash = <span className='text-muted-foreground'>—</span>

/** 是否切换了设备状态：true 已切换、false 未切换、无联动（null）显示「—」。 */
export function StateChangedCell({ row }: { row: MesRow }) {
  const v = alarmStateOf(row).state_changed
  if (v == null) return dash
  return v ? (
    <Badge variant='outline'>{t('mes.alarm.changed.yes')}</Badge>
  ) : (
    <Badge variant='secondary'>{t('mes.alarm.changed.no')}</Badge>
  )
}

/** 未切换的原因（三语，未知码原样）。 */
export function SkipReasonCell({ row }: { row: MesRow }) {
  const why = skipReasonText(alarmStateOf(row).state_skip_reason)
  return why ? <span>{why}</span> : dash
}
