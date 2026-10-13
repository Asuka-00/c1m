/** MES 表单必填规则与 422 错误消息翻译（与后端 required / required_when 一致）。 */
import { AxiosError } from 'axios'
import i18n, { t } from '@/i18n'
import { errorMessage } from '@/lib/api/client'
import type { MesEntity, MesField } from '@/lib/api/mes/common'
import { TERMINAL_STATUSES } from '@/features/mes/execution/lot-rules'
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

/**
 * 后端业务错误码（decisions N5：`detail: {code, message?, ...}`；
 * P01/P02/P14/P16、lot-state-machine v0.2）。
 */
export const MES_ERROR_CODES = [
  'on_hold',
  'lot_status',
  'lot_busy',
  'batch_blocked',
  'merge_source_invalid',
  'idempotency_in_progress',
  'idempotency_key_mismatch',
  'idempotency_key_reused',
] as const
type MesErrorCode = (typeof MES_ERROR_CODES)[number]
const isCode = (x: unknown): x is MesErrorCode =>
  typeof x === 'string' && (MES_ERROR_CODES as readonly string[]).includes(x)

const stageLabel = (action: string) =>
  i18n.exists(`mes.exec.stage.${action}`)
    ? t(`mes.exec.stage.${action}`)
    : action

/** lot_status：有动作与当前状态时给出具体句子，否则通用提示。 */
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
 * 兜底：旧格式的合批源校验原文（"duplicate lots or the target lot itself"）。
 * 后端按 N5 全部改为 `merge_source_invalid` 后可删除本正则及其使用处。
 */
const MERGE_SOURCES = /duplicate|repeated|target|重复|目标/i

/**
 * 兜底：旧格式字段级错误（422 `[{loc: ['body', 字段], msg}]`）中的业务错误翻译。
 * 后端按 N5 统一为 `detail: {code}` 后可删除。
 */
function fieldCodeMessage(name: string, rest: string): string | null {
  if (name === 'on_hold') return t('mes.err.code.on_hold')
  if (
    (name === 'lot_status' || name === 'source_lot_ids') &&
    MERGE_SOURCES.test(rest)
  )
    return t('mes.err.code.merge_source_invalid')
  if (name !== 'lot_status') return null
  const stage = /^cannot (\w+) a (\w+) lot$/.exec(rest)
  if (stage) return lotStatusMessage(stage[1], stage[2])
  const is = /^lot is (\w+)$/.exec(rest)
  if (is) return lotStatusMessage(undefined, is[1])
  return t('mes.err.code.lot_status')
}

/**
 * 业务错误码翻译：按 `detail.code` 识别（N5）。
 * `lot_status` 会用 `detail.action` / `detail.lot_status` 生成具体提示。
 *
 * @returns 本地化消息；不是已知错误码时为 null
 */
export function mesCodeMessage(err: unknown): string | null {
  if (!(err instanceof AxiosError) || !err.response) return null
  const d = (err.response.data as { detail?: unknown })?.detail
  if (!d || typeof d !== 'object' || Array.isArray(d)) return null
  const { code, action, lot_status } = d as Record<string, unknown>
  if (!isCode(code)) return null
  if (code === 'lot_status') return lotStatusMessage(action, lot_status)
  return t(`mes.err.code.${code}`)
}

/** 用实体字段标签翻译 MES 422 错误详情（"field: message"）。 */
export function mesErrorMessage(err: unknown, e: MesEntity | undefined) {
  const coded = mesCodeMessage(err)
  if (coded) return coded
  const d =
    err instanceof AxiosError && err.response?.status === 422
      ? (err.response.data as { detail?: unknown })?.detail
      : null
  if (!Array.isArray(d)) return errorMessage(err)
  const parse = (x: { loc?: string[]; msg?: string }) => {
    const msg = String(x.msg ?? '')
    const name = x.loc?.[1] ?? msg.split(':')[0]
    const rest = msg.slice(msg.indexOf(':') + 1).trim()
    return { name, rest }
  }
  // 全部是业务错误码时直接给出本地化提示（不加“校验失败”前缀）
  const codes = d.map((x) => {
    const { name, rest } = parse(x)
    return fieldCodeMessage(name, rest)
  })
  if (codes.every(Boolean)) return [...new Set(codes)].join('；')
  if (!e) return errorMessage(err)
  const msgs = d.map((x: { loc?: string[]; msg?: string }, i) => {
    const { name, rest } = parse(x)
    if (codes[i]) return codes[i]
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
