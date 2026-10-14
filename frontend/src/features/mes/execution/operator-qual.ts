/** P3 人员资质（D62）：有效期状态、预警天数、资质匹配优先级与进站检查说明。 */
import { t } from '@/i18n'
import type { MesRow } from '@/lib/api/mes/common'
import type { CheckResult } from '@/lib/api/mes/execution'
import { getSiteTz, toSiteDate } from '@/lib/site-tz'
import { daysUntil } from '@/features/mes/common/due'

/** 默认到期预警天数（D62-5：由后端设置下发 `warn_days`，读不到时用 30）。 */
export const QUAL_WARN_DAYS = 30

/** 预警天数合法范围（含两端）。 */
export const QUAL_WARN_DAYS_MIN = 1
export const QUAL_WARN_DAYS_MAX = 365

/** 后端下发的预警天数：须为 1–365 的整数；缺失或非法（含 0、负数、小数、超 365）一律用默认 30。 */
export function warnDaysOf(v: unknown): number {
  const n = typeof v === 'string' && v.trim() !== '' ? Number(v) : v
  return typeof n === 'number' &&
    Number.isInteger(n) &&
    n >= QUAL_WARN_DAYS_MIN &&
    n <= QUAL_WARN_DAYS_MAX
    ? n
    : QUAL_WARN_DAYS
}

export type QualState = 'inactive' | 'expired' | 'expiring' | 'valid'

/** 资质状态：停用 > 已过期 > 预警期内 > 有效；无到期日视为长期有效；expires_on 当天仍有效（D62-7）；按站点日期（D75）。 */
export function qualState(
  r: MesRow,
  today = new Date(),
  warnDays = QUAL_WARN_DAYS,
  tz: string = getSiteTz()
): QualState {
  if (r.is_active === false) return 'inactive'
  const exp = r.expires_on as string | null | undefined
  if (!exp) return 'valid'
  const n = daysUntil(exp, today, tz)
  if (n < 0) return 'expired'
  return n <= warnDays ? 'expiring' : 'valid'
}

/**
 * 选出适用的资质（D62-7）：同一人同一工序下，「工序+设备类型」匹配的优先于「只按工序」的；
 * 只考虑启用且未过期的记录。判定以后端检查为准，这里只用于界面提示。
 */
export function pickQual(
  rows: MesRow[],
  operationId: string,
  equipmentTypeId?: string | null,
  today = new Date(),
  tz: string = getSiteTz()
): MesRow | null {
  const ok = rows.filter(
    (r) =>
      r.operation_id === operationId &&
      !['inactive', 'expired'].includes(qualState(r, today, QUAL_WARN_DAYS, tz))
  )
  if (equipmentTypeId) {
    const exact = ok.find((r) => r.equipment_type_id === equipmentTypeId)
    if (exact) return exact
  }
  return ok.find((r) => !r.equipment_type_id) ?? null
}

/** operator_qualified 检查说明：不合格时本地化“不能进站、不可放行”，通过但临期时提示到期日。 */
export function operatorQualMessage(
  r: CheckResult,
  now: Date = new Date(),
  tz: string = getSiteTz()
): string | null {
  if (r.check_type !== 'operator_qualified') return null
  const s = (k: string) => {
    const v = r.data?.[k]
    return typeof v === 'string' ? v : ''
  }
  if (r.result !== 'pass')
    return t('mes.qual.notQualified', { user: s('user'), op: s('operation') })
  const exp = s('expires')
  if (exp && daysUntil(exp, now, tz) <= warnDaysOf(r.data?.warn_days))
    return t('mes.qual.expiringSoon', { date: toSiteDate(exp, tz) })
  return null
}
