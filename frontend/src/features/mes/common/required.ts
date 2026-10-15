/** MES 表单必填规则与 422 错误消息翻译（与后端 required / required_when 一致）。 */
import { AxiosError } from 'axios'
import { t } from '@/i18n'
import { errorMessage } from '@/lib/api/client'
import type { MesEntity, MesField } from '@/lib/api/mes/common'
import { entityLabel, enumLabel, fieldLabel } from './labels'

type V = Record<string, unknown>
const blank = (x: unknown) => x == null || x === ''

/** 使 `f` 必填的条件（同级字段 + 当前值）；
 *  无条件必填时为 `true`，可选时为 `null`。与后端的
 *  `required` / `required_when` 校验保持一致。 */
export function requiredBy(
  e: MesEntity,
  f: MesField,
  v: V
): true | { field: MesField; value: unknown } | null {
  if (f.required) return true
  for (const [name, allowed] of Object.entries(f.required_when ?? {})) {
    const other = e.fields.find((x) => x.name === name)
    if (!other) continue
    const cur = v[other.column]
    const on = allowed.includes('*') ? !blank(cur) : allowed.includes(cur)
    if (on) return { field: other, value: cur }
  }
  return null
}

const condText = (e: MesEntity, c: { field: MesField; value: unknown }) =>
  t('mes.err.requiredWhen', {
    cond: fieldLabel(e, c.field),
    value: c.field.enum
      ? enumLabel(c.field.enum, String(c.value))
      : t('mes.err.isSet'),
  })

/** 前端必填校验；返回 字段名 -> 错误消息。 */
export function validateRequired(e: MesEntity, v: V, skip: Set<string>) {
  const errs: Record<string, string> = {}
  for (const f of e.fields) {
    if (
      skip.has(f.column) ||
      f.default_from ||
      f.auto ||
      f.system ||
      f.type === 'bool'
    )
      continue
    const by = requiredBy(e, f, v)
    if (by && blank(v[f.column]))
      errs[f.name] = by === true ? t('mes.err.required') : condText(e, by)
  }
  return errs
}

/** 条件必填时显示在星号旁的提示。 */
export const requiredHint = (e: MesEntity, f: MesField, v: V) => {
  const by = requiredBy(e, f, v)
  return by && by !== true ? condText(e, by) : ''
}

const KNOWN: Record<string, string> = {
  "must match the parent equipment's type": 'mes.err.parentTypeMismatch',
  'the product already has a default route': 'mes.err.duplicateDefaultRoute',
  'needs an active route bound as default before activation':
    'mes.err.productNeedsDefaultRoute',
}

/** 用实体字段标签翻译 MES 422 错误详情（"field: message"）。 */
export function mesErrorMessage(err: unknown, e: MesEntity | undefined) {
  const d =
    err instanceof AxiosError && err.response?.status === 422
      ? (err.response.data as { detail?: unknown })?.detail
      : null
  if (!e || !Array.isArray(d)) return errorMessage(err)
  const msgs = d.map((x: { loc?: string[]; msg?: string }) => {
    const msg = String(x.msg ?? '')
    const name = x.loc?.[1] ?? msg.split(':')[0]
    const rest = msg.slice(msg.indexOf(':') + 1).trim()
    const label = e.fields.some((f) => f.name === name)
      ? fieldLabel(e, name)
      : entityLabel(name)
    const m = /^required when (\w+) = (.+)$/.exec(rest)
    if (rest === 'required') return `${label}: ${t('mes.err.required')}`
    if (m) {
      const other = e.fields.find((f) => f.name === m[1])
      return `${label}: ${
        other
          ? condText(e, { field: other, value: m[2] === 'set' ? 'x' : m[2] })
          : rest
      }`
    }
    return `${label}: ${KNOWN[rest] ? t(KNOWN[rest]) : rest}`
  })
  return `${t('errors.validation')} ${msgs.join('；')}`
}
