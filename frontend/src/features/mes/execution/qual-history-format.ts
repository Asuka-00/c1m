/** 资质履历的显示格式（P3-F2）。 */
import { AxiosError } from 'axios'
import { t } from '@/i18n'
import { errorMessage } from '@/lib/api/client'
import type { QualLogRow } from '@/lib/api/mes/qual-history'

export const dash = (v: unknown) =>
  v == null || v === '' ? '—' : typeof v === 'boolean' ? String(v) : String(v)

/** 变更摘要：字段: 旧 → 新（字段名取实体字段翻译，没有时原样）。 */
export function qualChanges(r: Pick<QualLogRow, 'before' | 'after'>): string {
  const keys = [
    ...new Set([...Object.keys(r.before ?? {}), ...Object.keys(r.after ?? {})]),
  ]
  return keys
    .map((k) => {
      const label = t(`mes.qualHistory.field.${k}`, { defaultValue: k })
      const a = r.before?.[k]
      const b = r.after?.[k]
      return r.before
        ? `${label}: ${dash(a)} → ${dash(b)}`
        : `${label}: ${dash(b)}`
    })
    .join('；')
}

/** 资质写入错误文案（D85：self_approval / holder_approval），其余走通用。 */
export function qualErrorMessage(e: unknown): string {
  return qualReasonMessage(e) ?? errorMessage(e)
}

/** 只识别资质专属 reason；不认识返回 null，交给调用方的通用文案（QA P2-1）。 */
export function qualReasonMessage(e: unknown): string | null {
  if (e instanceof AxiosError) {
    const d = (e.response?.data as { detail?: unknown })?.detail
    if (Array.isArray(d)) {
      const r = (d as { ctx?: { reason?: unknown } }[]).find(
        (x) =>
          x?.ctx?.reason === 'self_approval' ||
          x?.ctx?.reason === 'holder_approval' ||
          x?.ctx?.reason === 'conflicting_fields'
      )?.ctx?.reason
      if (r === 'self_approval') return t('mes.qualHistory.err.selfApproval')
      if (r === 'holder_approval')
        return t('mes.qualHistory.err.holderApproval')
      if (r === 'conflicting_fields')
        return t('mes.qualHistory.err.conflictingFields')
    }
  }
  return null
}
