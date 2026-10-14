/** MES 表单必填规则与 422 错误消息翻译（与后端 required / required_when 一致）。 */
import { AxiosError } from 'axios'
import i18n, { t } from '@/i18n'
import { codeItemText, errorMessage, queryItemText } from '@/lib/api/client'
import type { MesEntity, MesField } from '@/lib/api/mes/common'
import { parseDecimal } from '@/lib/decimal'
import { TERMINAL_STATUSES } from '@/features/mes/execution/lot-rules'
import { entityLabel, enumLabel, fieldLabel } from './labels'

type V = Record<string, unknown>
const blank = (x: unknown) => x == null || x === ''

/**
 * 前端补充的条件必填 / 仅允许（后端由校验器而非元数据 required_when 表达时用）。
 * D59：alarm_code.target_state 仅在 action=set_state 时必填，action=none 时不能填。
 */
export const ONLY_WHEN: Record<string, Record<string, [string, unknown[]]>> = {
  alarm_code: { target_state: ['action', ['set_state']] },
}

/** 使 `f` 必填的条件（同级字段 + 当前值）；
 *  无条件必填时为 `true`，可选时为 `null`。与后端的
 *  `required` / `required_when` 校验保持一致。 */
export function requiredBy(
  e: MesEntity,
  f: MesField,
  v: V
): true | { field: MesField; value: unknown } | null {
  if (f.required) return true
  const extra = ONLY_WHEN[e.code]?.[f.name]
  const when = {
    ...(extra ? { [extra[0]]: extra[1] } : {}),
    ...(f.required_when ?? {}),
  }
  for (const [name, allowed] of Object.entries(when)) {
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
    const only = ONLY_WHEN[e.code]?.[f.name]
    if (!by && only && !blank(v[f.column])) {
      const other = e.fields.find((x) => x.name === only[0])
      if (other)
        errs[f.name] = t('mes.err.onlyWhen', {
          cond: fieldLabel(e, other),
          value: other.enum
            ? enumLabel(other.enum, String(only[1][0]))
            : String(only[1][0]),
        })
    }
  }
  return errs
}

/** 定点数字段的最大小数位（D60：numeric(18,6)，超过 6 位后端 422 too_many_decimals）。 */
export const MAX_DECIMALS = 6

/**
 * 字段的最大小数位（D60）：优先元数据 `decimal_places`；为 null 表示普通浮点、不限位数。
 * 旧后端不带 `decimal_places` 时退回 `scale`（也没有时不限）。
 */
export function decimalLimit(f: MesField): number | null {
  if (f.decimal_places !== undefined) return f.decimal_places
  return f.scale ?? null
}

/** 提前校验小数位：先去掉末尾 0 再数位数（1.1000000 算 1 位），超过 decimal_places 时提示。 */
export function validateDecimals(e: MesEntity, v: V, skip: Set<string>) {
  const errs: Record<string, string> = {}
  for (const f of e.fields) {
    if (f.type !== 'float' || skip.has(f.column) || f.system) continue
    const raw = v[f.column]
    if (raw == null || raw === '') continue
    const n = decimalLimit(f)
    if (n == null) continue
    const d = parseDecimal(String(raw))
    if (d && d.decimals > n) errs[f.name] = t('mes.err.tooManyDecimals', { n })
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
  'rework_route_missing',
  'qtime_rule_in_use',
  'hold_not_found',
  'qtime_action_invalid',
  'idempotency_in_progress',
  'idempotency_key_mismatch',
  'idempotency_key_reused',
  'too_many_decimals',
  'date_range_too_large',
  'read_only_field',
  'unknown_field',
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
  // D59：alarm_code.target_state 后端英文校验消息
  if (name === 'target_state') {
    if (/^required when action=set_state$/.test(rest))
      return t('mes.alarm.err.targetRequired')
    if (/^only allowed when action=set_state$/.test(rest))
      return t('mes.alarm.err.targetOnly')
    const u = /^unknown E10 state (.*)$/.exec(rest)
    if (u) return t('mes.alarm.err.targetUnknown', { state: u[1] })
  }
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
  return t(`mes.err.code.${code}`, codeParams(d as Record<string, unknown>))
}

/** 错误码文案可用的插值字段（白名单）；detail 的其他键不传给翻译函数。 */
export const CODE_PARAMS = [
  'qtime_rule_code',
  'hold_count',
  'hold_id',
  'action',
] as const

/** 从错误 detail 中只取白名单内的插值参数。 */
export function codeParams(d: Record<string, unknown>) {
  const out: Record<string, unknown> = {}
  for (const k of CODE_PARAMS) if (d[k] != null) out[k] = d[k]
  return out
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
  const isQuery = (x: { loc?: unknown[] }) => x.loc?.[0] === 'query'
  const parse = (x: { loc?: string[]; msg?: string }) => {
    const msg = String(x.msg ?? '')
    const name = x.loc?.[1] ?? msg.split(':')[0]
    const rest = msg.slice(msg.indexOf(':') + 1).trim()
    return { name, rest }
  }
  // 全部是业务错误码时直接给出本地化提示（不加“校验失败”前缀）
  const tooMany = (x: { type?: string; code?: string }) =>
    x.code === 'too_many_decimals' || x.type === 'too_many_decimals'
  // 通用字段级 422 码（OQ-20 read_only_field、unknown_field）→ 三语文案
  const FIELD_CODES: Record<string, string> = {
    read_only_field: 'mes.err.readOnlyField',
    unknown_field: 'mes.err.unknownField',
  }
  const fieldCode = (x: { type?: string; code?: string }) =>
    FIELD_CODES[x.code ?? ''] ?? FIELD_CODES[x.type ?? '']
  const codes = d.map((x) => {
    const { name, rest } = parse(x)
    // D65：查询参数 422（sort_by、筛选值等）不映射表单字段
    if (!fieldCode(x) && !tooMany(x)) {
      // 固定码（如 date_range_too_large）按码取文案；查询参数不映射表单字段
      const ct = codeItemText(x)
      if (ct) return ct
      if (isQuery(x)) return queryItemText(x)
    }
    const fk = fieldCode(x)
    if (fk) {
      // 查询参数（loc[0]='query'）不映射到表单字段，前缀参数名
      const f = isQuery(x) ? undefined : e?.fields.find((y) => y.name === name)
      const msg = isQuery(x) ? `${name}: ${t(fk)}` : t(fk)
      return e && f ? `${fieldLabel(e, name)}: ${msg}` : msg
    }
    if (tooMany(x)) {
      const f = e?.fields.find((y) => y.name === name)
      const msg = t('mes.err.tooManyDecimals', {
        n: (f && decimalLimit(f)) ?? MAX_DECIMALS,
      })
      return e && f ? `${fieldLabel(e, name)}: ${msg}` : msg
    }
    return fieldCodeMessage(name, rest)
  })
  if (codes.every(Boolean)) return [...new Set(codes)].join('；')
  if (!e) return errorMessage(err)
  const msgs = d.map((x: { loc?: string[]; msg?: string }, i) => {
    const { name, rest } = parse(x)
    if (codes[i]) return codes[i]
    const label =
      !isQuery(x) && e.fields.some((f) => f.name === name)
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
