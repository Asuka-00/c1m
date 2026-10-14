/** P3 人员资质（草案）：有效期状态与进站资质检查的本地化说明。 */
import { t } from '@/i18n'
import type { MesRow } from '@/lib/api/mes/common'
import type { CheckResult } from '@/lib/api/mes/execution'
import { daysUntil } from '@/features/mes/common/due'

/** 到期预警天数（前端假设，待确认是否由后端 qual_expiry_notice 配置下发）。 */
export const QUAL_WARN_DAYS = 30

export type QualState = 'inactive' | 'expired' | 'expiring' | 'valid'

/** 资质状态：停用 > 已过期 > 预警期内 > 有效；无到期日视为长期有效。 */
export function qualState(r: MesRow, today = new Date()): QualState {
  if (r.is_active === false) return 'inactive'
  const exp = r.expires_on as string | null | undefined
  if (!exp) return 'valid'
  const n = daysUntil(exp, today)
  if (n < 0) return 'expired'
  return n <= QUAL_WARN_DAYS ? 'expiring' : 'valid'
}

/** operator_qualified 检查说明：不合格时本地化“不能进站”，通过但临期时提示到期日。 */
export function operatorQualMessage(r: CheckResult): string | null {
  if (r.check_type !== 'operator_qualified') return null
  const s = (k: string) => {
    const v = r.data?.[k]
    return typeof v === 'string' ? v : ''
  }
  if (r.result !== 'pass')
    return t('mes.qual.notQualified', { user: s('user'), op: s('operation') })
  const exp = s('expires')
  if (exp && daysUntil(exp) <= QUAL_WARN_DAYS)
    return t('mes.qual.expiringSoon', { date: exp.slice(0, 10) })
  return null
}
