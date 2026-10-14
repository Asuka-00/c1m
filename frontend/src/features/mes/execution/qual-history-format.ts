/** 资质履历的显示格式（P3-F2）。 */
import { t } from '@/i18n'
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
