import { AxiosError } from 'axios'
import { t } from '@/i18n'
import { errorMessage } from '@/lib/api/client'
import type { MesEntity, MesField } from '@/lib/api/mes'
import { entityLabel, enumLabel, fieldLabel } from './labels'

type V = Record<string, unknown>
const blank = (x: unknown) => x == null || x === ''

/** The condition (sibling field + current value) that makes `f` required, or
 *  `true` when unconditionally required, `null` when optional. Mirrors the
 *  backend's `required` / `required_when` checks. */
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

/** Client-side required check; field name -> message. */
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

/** Hint shown next to the asterisk for conditional requirements. */
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

/** Translate MES 422 details ("field: message") with entity field labels. */
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
