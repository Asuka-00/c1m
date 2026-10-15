import { t } from '@/i18n'
import type { MapApiError } from '@/lib/api/mes/map'

/** 接口错误 → 一句提示（逐行错误另外列表显示）。 */
export function mapErrorMessage(e: MapApiError): string {
  switch (e.kind) {
    case 'conflict':
      return t('mes.map.conflict')
    case 'too_large':
      return t('mes.map.tooLarge')
    case 'forbidden':
      return t('mes.map.forbidden')
    case 'not_found':
      return t('mes.map.notFound')
    case 'fields':
      return e.fields.map((f) => `${f.field}: ${f.msg}`).join('; ')
    case 'rows':
      return t('mes.map.hasErrors', { n: e.errors.length })
    default:
      return e.message || t('mes.map.importFailed')
  }
}
