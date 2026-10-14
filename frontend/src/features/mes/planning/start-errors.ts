/**
 * 开批接口 422 → 按批次行定位的字段错误（F6 补充）。
 *
 * 后端（planning/service.py、lot/customer.py、Pydantic 严格载荷）一次返回全部错误，
 * loc 形如 `["body","lots",i,"customer_id"]`，i 从 0 开始，与请求里 lots 的下标（即向导行号）一致。
 */
import { AxiosError } from 'axios'
import { t } from '@/i18n'

/** 第 i 行（从 0 开始）的字段错误：字段名 → 提示。 */
export type LotFieldErrors = Record<number, Record<string, string>>

interface Item {
  loc?: unknown[]
  msg?: string
  type?: string
}

const RULES: [RegExp | string, string][] = [
  ['extra_forbidden', 'mes.start.fe.notAllowed'],
  [/customer required/, 'mes.start.fe.customerRequired'],
  [/customer not found/, 'mes.start.fe.customerNotFound'],
  [/customer only for ownership/, 'mes.start.fe.customerOwnOnly'],
  [/customer lot no\. only for ownership/, 'mes.start.fe.customerLotOwnOnly'],
  [/qty must be/, 'mes.start.fe.qty'],
  [/carrier/, 'mes.start.fe.carrier'],
  [/slot/, 'mes.start.fe.slots'],
  [/at most 100|max_length|too long/i, 'mes.start.fe.tooLong'],
]

function message(it: Item): string {
  const msg = it.msg ?? ''
  for (const [re, key] of RULES)
    if (typeof re === 'string' ? it.type === re : re.test(msg)) return t(key)
  if (it.type === 'string_too_long') return t('mes.start.fe.tooLong')
  return t('mes.start.fe.invalid')
}

/** 解析开批 422；没有能定位到批次行的错误时返回 null（交给通用提示）。 */
export function startFieldErrors(e: unknown): LotFieldErrors | null {
  if (!(e instanceof AxiosError) || e.response?.status !== 422) return null
  const d = (e.response.data as { detail?: unknown })?.detail
  if (!Array.isArray(d)) return null
  const out: LotFieldErrors = {}
  for (const it of d as Item[]) {
    const loc = it.loc ?? []
    const p = loc[0] === 'body' ? loc.slice(1) : loc
    if (p[0] !== 'lots' || typeof p[1] !== 'number') continue
    const field = String(p[2] ?? 'qty')
    const row = (out[p[1]] ??= {})
    row[field] ??= message(it)
  }
  return Object.keys(out).length ? out : null
}
