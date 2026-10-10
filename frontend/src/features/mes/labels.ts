import { t } from '@/i18n'
import type { MesEntity, MesField } from '@/lib/api/mes'

/** Labels come from the generated bundles (locales/mes/*.json). */
export const entityLabel = (code: string) =>
  t(`mes.entity.${code}`, { defaultValue: code })
export const fieldLabel = (e: MesEntity, f: MesField | string) => {
  const name = typeof f === 'string' ? f : f.name
  return t(`mes.field.${e.code}.${name}`, { defaultValue: name })
}
export const fieldHelp = (e: MesEntity, f: MesField) =>
  f.help ? t(`mes.help.${e.code}.${f.name}`, { defaultValue: '' }) : ''
export const enumLabel = (en: string, v: string) =>
  en === 'entity_type'
    ? entityLabel(v)
    : t(`mes.enum.${en}.${v}`, { defaultValue: v })
export const statusLabel = (v: string) => enumLabel('status', v)

export const rowLabel = (r: Record<string, unknown>, labelField = 'code') => {
  let s = String(r[labelField] ?? r.id)
  if (r.version != null) s += ` v${r.version}`
  if (labelField === 'code' && r.name) s += ` · ${r.name}`
  else if (labelField !== 'code' && r.operation_label)
    s += ` · ${String(r.operation_label).split(' · ')[0]}`
  return s
}
