/**
 * D58 / D59：报警联动切设备状态的结果说明。
 * 后端（752503e）在报警登记响应 / EAP 事件 result 中给 `state_changed` 与英文 `state_skip_reason`
 * （`unknown E10 state X` / `already X` / `A -> B not allowed`），这里翻成三语；无法识别时原样附上。
 */
import { t } from '@/i18n'

export interface AlarmStateResult {
  state_changed?: boolean | null
  state_skip_reason?: string | null
}

/** 未执行联动的原因（三语）。 */
export function skipReasonText(why: string | null | undefined): string {
  const s = (why ?? '').trim()
  if (!s) return ''
  let m = /^unknown E10 state (.+)$/.exec(s)
  if (m) return t('mes.alarm.skip.unknown', { state: m[1] })
  m = /^already (.+)$/.exec(s)
  if (m) return t('mes.alarm.skip.already', { state: m[1] })
  m = /^(.+?) -> (.+?) not allowed$/.exec(s)
  if (m) return t('mes.alarm.skip.notAllowed', { from: m[1], to: m[2] })
  return s
}

/** state_changed=false 时的说明；切换成功或不涉及联动（无字段）时为 null。 */
export function alarmStateNote(r: AlarmStateResult | null | undefined) {
  if (!r || r.state_changed !== false) return null
  const why = skipReasonText(r.state_skip_reason)
  return why
    ? t('mes.alarm.stateSkipped', { why })
    : t('mes.alarm.stateUnchanged')
}
