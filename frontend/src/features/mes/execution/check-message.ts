/** 检查结果说明的本地化（后端 message 为英文原文）。 */
import { t } from '@/i18n'
import type { CheckResult } from '@/lib/api/mes/execution'
import { operatorQualMessage } from './operator-qual'
import { toolLifeMessage } from './tool-life'

/** 检查结果说明：已知检查类型用本地化文案，其余显示后端原文。 */
export function checkMessage(r: CheckResult): string {
  if (r.check_type === 'eqp_wait_qual' && r.result !== 'pass') {
    const eq = r.data?.equipment
    return t('mes.exec.checkMsg.eqp_wait_qual', {
      equipment: typeof eq === 'string' ? eq : '',
    })
  }
  // D78 Q5：打标检验不合格未处理，不能出站，不可强制放行
  if (r.check_type === 'marking_inspection' && r.result !== 'pass') {
    const code = r.data?.trace_code
    return t('mes.marking.checkBlocked', {
      trace: typeof code === 'string' ? code : '—',
    })
  }
  if (r.check_type === 'tool_life' && r.result !== 'pass')
    return toolLifeMessage(r)
  const qual = operatorQualMessage(r)
  if (qual) return qual
  if (r.result !== 'pass') {
    const list = reasonTexts(r.reasons)
    if (list.length > 1) return list.join('；')
    if (r.reason) return r.reason
    if (list.length) return list[0]
  }
  return r.message
}

/** reasons[] 元素取文案（字符串或 {message|reason|code}）。 */
export function reasonTexts(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v
    .map((x) => {
      if (typeof x === 'string') return x
      if (x && typeof x === 'object') {
        const o = x as Record<string, unknown>
        const m = o.message ?? o.reason ?? o.code
        return typeof m === 'string' ? m : ''
      }
      return ''
    })
    .filter(Boolean)
}
