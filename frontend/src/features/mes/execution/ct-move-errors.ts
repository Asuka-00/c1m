import { AxiosError } from 'axios'
import { t } from '@/i18n'
import { mesErrorMessage } from '@/features/mes/common/required'

/** 报表错误：404 为工序 / 产品不存在（P3-B5），其余走通用（date_range_too_large / range_inverted 等）。 */
export function ctMoveErrorMessage(e: unknown) {
  if (e instanceof AxiosError && e.response?.status === 404)
    return t('mes.ctMove.notFound')
  return mesErrorMessage(e, undefined)
}
