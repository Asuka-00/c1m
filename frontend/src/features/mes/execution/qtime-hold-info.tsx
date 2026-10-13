/** Q-Time 自动 Hold 的附加信息（D20）：规则、起止工步与超时时长；字段全为空时不渲染。 */
import { t } from '@/i18n'
import {
  fmtOverdue,
  hasQtimeInfo,
  type QtimeHoldFields,
  type StepNames,
} from './qtime-hold'

export function QtimeHoldInfo({
  hold,
  steps = {},
}: {
  hold: QtimeHoldFields
  steps?: StepNames
}) {
  if (!hasQtimeInfo(hold)) return null
  const step = (id?: string | null) => (id ? (steps[id] ?? id) : '—')
  const overdue = hold.qtime_overdue_seconds
  return (
    <div
      className='space-y-0.5 text-xs text-muted-foreground'
      data-testid='qtime-hold-info'
    >
      {overdue != null && overdue > 0 && (
        <div className='font-medium text-destructive'>
          {t('mes.qtimeHold.overdue', { time: fmtOverdue(overdue) })}
        </div>
      )}
      {(hold.qtime_from_step_id || hold.qtime_to_step_id) && (
        <div>
          {t('mes.qtimeHold.steps', {
            from: step(hold.qtime_from_step_id),
            to: step(hold.qtime_to_step_id),
          })}
        </div>
      )}
      {hold.qtime_rule_id && (
        <div className='break-all'>
          {t('mes.qtimeHold.rule')}:{' '}
          <span className='font-mono'>{hold.qtime_rule_id}</span>
        </div>
      )}
    </div>
  )
}
