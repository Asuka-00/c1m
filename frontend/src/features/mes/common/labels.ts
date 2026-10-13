/** MES 标签工具：实体、字段、枚举、行的多语言显示文本。 */
import i18n, { t } from '@/i18n'
import type { MesEntity, MesField } from '@/lib/api/mes/common'
import { splitLabel } from '@/lib/split-label'

/** 标签来自生成的语言包（locales/mes/*.json）。 */
export const entityLabel = (code: string) =>
  t(`mes.entity.${code}`, { defaultValue: code })
/** 字段标签（按当前语言，缺失时回退字段名）。 */
export const fieldLabel = (e: MesEntity, f: MesField | string) => {
  const name = typeof f === 'string' ? f : f.name
  return t(`mes.field.${e.code}.${name}`, { defaultValue: name })
}
/** 字段帮助文本（字段声明了 help 时）。 */
export const fieldHelp = (e: MesEntity, f: MesField) =>
  f.help ? t(`mes.help.${e.code}.${f.name}`, { defaultValue: '' }) : ''
/**
 * 枚举值标签。
 *
 * @param en - 枚举名（entity_type 时显示实体标签）
 * @param v - 枚举值
 */
export const enumLabel = (en: string, v: string) =>
  en === 'entity_type'
    ? entityLabel(v)
    : t(`mes.enum.${en}.${v}`, { defaultValue: v })
/** 版本状态标签。 */
export const statusLabel = (v: string) => enumLabel('status', v)

/** 行的显示文本：编码（含版本号 vN）+ 名称。 */
export const rowLabel = (r: Record<string, unknown>, labelField = 'code') => {
  let s = String(r[labelField] ?? r.id)
  if (r.version != null) s += ` v${r.version}`
  if (labelField === 'code' && r.name) s += ` · ${r.name}`
  else if (labelField !== 'code' && r.operation_label)
    s += ` · ${String(r.operation_label).split(' · ')[0]}`
  return s
}

/** 简单选项对象的 `code · name` 显示文本。 */
export const optLabel = (o: { code: string; name?: string }) =>
  o.name ? `${o.code} · ${o.name}` : o.code

/** 系统内置原因码（如 Q-Time 超时 Hold 的 qtime_expired，M1）的本地化名称；其他原因码沿用主数据名称。 */
export const reasonName = (code: string, name?: string | null) =>
  i18n.exists(`mes.reasonCode.${code}`)
    ? t(`mes.reasonCode.${code}`)
    : (name ?? '')

/** 原因码选项标签（“编码 · 名称”，内置原因码名称本地化）。 */
export const reasonOptLabel = (o: { code: string; name?: string }) => {
  const n = reasonName(o.code, o.name)
  return n ? `${o.code} · ${n}` : o.code
}

/** 后端 `reason_label`（“编码 · 名称”）的本地化显示。 */
export const reasonLabel = (label: unknown) => {
  const [code, name] = splitLabel(label)
  return code ? reasonOptLabel({ code, name }) : ''
}
