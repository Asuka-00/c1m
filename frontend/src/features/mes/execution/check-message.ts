/** 检查结果说明的本地化（后端 message 为英文原文）。 */
import { t } from '@/i18n'
import type { CheckResult } from '@/lib/api/mes/execution'

/** 检查结果说明：已知检查类型用本地化文案，其余显示后端原文。 */
export function checkMessage(r: CheckResult): string {
  if (r.check_type === 'eqp_wait_qual' && r.result !== 'pass') {
    const eq = r.data?.equipment
    return t('mes.exec.checkMsg.eqp_wait_qual', {
      equipment: typeof eq === 'string' ? eq : '',
    })
  }
  return r.message
}
