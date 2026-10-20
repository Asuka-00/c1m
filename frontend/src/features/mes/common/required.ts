/** MES 表单必填规则与 422 错误消息翻译（与后端 required / required_when 一致）。 */
import { AxiosError } from 'axios'
import i18n, { t } from '@/i18n'
import { errorMessage } from '@/lib/api/client'
import type { MesEntity, MesField } from '@/lib/api/mes/common'
import {
  codeText,
  detailParams,
  itemField,
  itemText,
  type CodedItem,
} from '@/lib/backend-text'
import { ErrorCode } from '@/lib/error-codes'
import { TERMINAL_STATUSES } from '@/features/mes/execution/shared/lot-rules'
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

const stageLabel = (action: string) =>
  i18n.exists(`mes.exec.stage.${action}`)
    ? t(`mes.exec.stage.${action}`)
    : action

/** 批次状态错误：有动作与当前状态时给出具体句子，否则通用提示。 */
function lotStatusMessage(action?: unknown, status?: unknown) {
  const st = typeof status === 'string' ? status : ''
  if (st && (TERMINAL_STATUSES as readonly string[]).includes(st))
    return t('mes.err.code.lot_status_is', {
      status: enumLabel('lot_status', st),
    })
  if (st && typeof action === 'string' && action)
    return t('mes.err.code.lot_status_stage', {
      stage: stageLabel(action),
      status: enumLabel('lot_status', st),
    })
  return t('mes.err.code.lot_status')
}

/**
 * 业务错误码翻译：`detail = {code, message, params}`；
 * 批次状态错误（`LOT_STATUS`）按 `action` / `lot_status` 生成具体提示，其余按 `error.code_<code>` 翻译。
 *
 * @returns 本地化消息；不是错误码或没有译文时为 null
 */
export function mesCodeMessage(err: unknown): string | null {
  if (!(err instanceof AxiosError) || !err.response) return null
  const d = (err.response.data as { detail?: unknown })?.detail
  if (!d || typeof d !== 'object' || Array.isArray(d)) return null
  const code = (d as Record<string, unknown>).code
  if (typeof code !== 'number') return null
  const p = detailParams(d as Record<string, unknown>)
  if (code === ErrorCode.LOT_STATUS)
    return lotStatusMessage(p.action, p.lot_status)
  return codeText(code, p)
}

/** 用实体字段标签翻译 MES 422 错误详情（每项 `code` + `params`）。 */
export function mesErrorMessage(err: unknown, e: MesEntity | undefined) {
  const coded = mesCodeMessage(err)
  if (coded) return coded
  const d =
    err instanceof AxiosError && err.response?.status === 422
      ? (err.response.data as { detail?: unknown })?.detail
      : null
  if (!Array.isArray(d)) return errorMessage(err)
  const label = (name: string) =>
    !e
      ? name
      : e.fields.some((f) => f.name === name)
        ? fieldLabel(e, name)
        : entityLabel(name)
  const text = (x: CodedItem) => {
    if (x.code === ErrorCode.FIELD_REQUIRED_WHEN && e) {
      // 条件必填：用实体字段标签和枚举标签生成“当 X 为 Y 时必填”
      const other = e.fields.find((f) => f.name === x.params?.when)
      if (other) {
        const value = x.params?.value === 'set' ? 'x' : x.params?.value
        return `${label(itemField(x))}: ${condText(e, { field: other, value })}`
      }
    }
    return itemText(x, label)
  }
  const texts = (d as CodedItem[]).map(text)
  // 全部是业务错误码时直接给出本地化提示（不加“校验失败”前缀）
  if (texts.every(Boolean)) return [...new Set(texts)].join('；')
  if (!e) return errorMessage(err)
  const msgs = (d as CodedItem[]).map(
    (x, i) => texts[i] ?? `${label(itemField(x))}: ${x.msg ?? ''}`
  )
  return `${t('error.validation')} ${msgs.join('；')}`
}
