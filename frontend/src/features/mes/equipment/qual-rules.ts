/** F5 待 Qual 规则：qual_state 判定与 Qual 登记错误翻译（D33 / D34）。 */
import { AxiosError } from 'axios'
import { t } from '@/i18n'
import { enumLabel } from '@/features/mes/common/labels'

export const WAIT_QUAL = 'wait_qual'

/** 是否待 Qual。 */
export const isWaitQual = (r: { qual_state?: string | null }) =>
  r.qual_state === WAIT_QUAL

/** Qual 登记错误 → 本地化提示（D34：403 不带字段细节）。 */
export function qualError(e: unknown): string {
  if (!(e instanceof AxiosError)) return t('errors.generic')
  if (!e.response) return t('errors.network')
  const { status } = e.response
  const d = (e.response.data as { detail?: unknown })?.detail
  if (status === 403) return t('mes.eqp.qual.err.forbidden')
  if (status === 404) return t('mes.eqp.qual.err.notFound')
  if (status === 409) {
    const o = d && typeof d === 'object' ? (d as Record<string, unknown>) : {}
    if (o.code === 'qual_task_closed') {
      const st = typeof o.qual_status === 'string' ? o.qual_status : ''
      return st
        ? t('mes.eqp.qual.err.closedAs', {
            status: enumLabel('qual_status', st),
          })
        : t('mes.eqp.qual.err.closed')
    }
    return t('mes.eqp.qual.err.conflict')
  }
  if (status === 422) return t('mes.eqp.qual.err.invalid')
  if (status >= 500) return t('errors.server')
  return t('errors.generic')
}
