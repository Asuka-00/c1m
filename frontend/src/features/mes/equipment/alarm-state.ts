/**
 * D58 / D59：报警联动切设备状态的结果说明。
 * 后端 baf7b55 起 `state_skip_reason` 是错误码（D59 补充）：`unknown_state` / `already_in_state` /
 * `transition_not_allowed`，报警登记响应、EAP 事件 result 和报警履历（`state_changed` /
 * `state_skip_reason`）都用这三个码。这里翻成三语；未知码原样显示。
 */
import { t } from '@/i18n'

export interface AlarmStateResult {
  state_changed?: boolean | null
  state_skip_reason?: string | null
}

/** D59 补充登记的跳过原因码。 */
export const SKIP_REASON_CODES = [
  'unknown_state',
  'already_in_state',
  'transition_not_allowed',
] as const

/** 未执行联动的原因（三语）；未知码兜底显示原码。 */
export function skipReasonText(why: string | null | undefined): string {
  const s = (why ?? '').trim()
  if (!s) return ''
  return (SKIP_REASON_CODES as readonly string[]).includes(s)
    ? t(`mes.alarm.skip.${s}`)
    : s
}

/** state_changed=false 时的说明；切换成功或不涉及联动（无字段）时为 null。 */
export function alarmStateNote(r: AlarmStateResult | null | undefined) {
  if (!r || r.state_changed !== false) return null
  const why = skipReasonText(r.state_skip_reason)
  return why
    ? t('mes.alarm.stateSkipped', { why })
    : t('mes.alarm.stateUnchanged')
}

/** 报警履历行的联动结果：优先顶层字段，旧数据退回 `e10_change` 里的同名字段。 */
export function alarmStateOf(r: Record<string, unknown>): AlarmStateResult {
  // 460df8f 起列表 / 详情顶层都有这两个字段：有顶层就整体用顶层（null 也不退回）
  if ('state_changed' in r || 'state_skip_reason' in r)
    return {
      state_changed: r.state_changed as boolean | null,
      state_skip_reason: (r.state_skip_reason as string | null) ?? null,
    }
  const ch = (r.e10_change ?? {}) as AlarmStateResult
  return {
    state_changed: ch.state_changed,
    state_skip_reason: ch.state_skip_reason,
  }
}
