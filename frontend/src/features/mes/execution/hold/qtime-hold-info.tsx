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
  // 优先用后端返回的工步名，其次用调用方提供的工步列表，最后显示 id
  const step = (id?: string | null, name?: string | null) =>
    name || (id ? (steps[id] ?? id) : '—')
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
      {(hold.qtime_from_step_id ||
        hold.qtime_to_step_id ||
        hold.qtime_from_step_name ||
        hold.qtime_to_step_name) && (
        <div>
          {t('mes.qtimeHold.steps', {
            from: step(hold.qtime_from_step_id, hold.qtime_from_step_name),
            to: step(hold.qtime_to_step_id, hold.qtime_to_step_name),
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
