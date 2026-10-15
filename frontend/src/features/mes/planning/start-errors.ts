/**
 * 开批接口 422 → 按批次行定位的字段错误（F6 补充）。
 *
 * 后端（planning/service.py、lot/customer.py、Pydantic 严格载荷）一次返回全部错误，
 * loc 形如 `["body","lots",i,"customer_id"]`，i 从 0 开始，与请求里 lots 的下标（即向导行号）一致。
 */
import { AxiosError } from 'axios'
import { t } from '@/i18n'
import { isParamLoc, queryItemText } from '@/lib/api/client'

/** 第 i 行（从 0 开始）的字段错误：字段名 → 提示。 */
export type LotFieldErrors = Record<number, Record<string, string>>

interface Item {
  loc?: unknown[]
  msg?: string
  type?: string
  code?: string
}

const RULES: [RegExp | string, string][] = [
  ['extra_forbidden', 'mes.start.fe.notAllowed'],
  ['customer_lot_required', 'mes.start.fe.customerLotRequired'],
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
    if (
      typeof re === 'string' ? it.type === re || it.code === re : re.test(msg)
    )
      return t(key)
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
    if (isParamLoc(it)) continue
    const p = loc[0] === 'body' ? loc.slice(1) : loc
    if (p[0] !== 'lots' || typeof p[1] !== 'number') continue
    const field = String(p[2] ?? 'qty')
    const row = (out[p[1]] ??= {})
    row[field] ??= message(it)
  }
  return Object.keys(out).length ? out : null
}

const TOP_RULES: [RegExp, string][] = [
  [/no active default route/, 'mes.start.fe.noRoute'],
  [/no operation steps|has no steps/, 'mes.start.fe.noSteps'],
  [/has no active BOM/, 'mes.start.fe.noBom'],
]

/**
 * 开批 422 中不属于某个批次行的错误（9c5e568：`["body","route"]`、`["body","bom"]` 即 bom_required 等），
 * 本地化后显示在页面顶部，不随行错误丢失。
 */
export function startTopErrors(e: unknown): string[] {
  if (!(e instanceof AxiosError) || e.response?.status !== 422) return []
  const d = (e.response.data as { detail?: unknown })?.detail
  if (!Array.isArray(d)) return []
  const out: string[] = []
  for (const it of d as Item[]) {
    const loc = it.loc ?? []
    if (isParamLoc(it)) {
      out.push(queryItemText(it))
      continue
    }
    const p = loc[0] === 'body' ? loc.slice(1) : loc
    if (p[0] === 'lots' && typeof p[1] === 'number') continue
    const msg = it.msg ?? ''
    const hit = TOP_RULES.find(([re]) => re.test(msg))
    if (!hit) {
      out.push(msg)
      continue
    }
    // "bom: P-001 has no active BOM" → 带上产品编码
    const product = /^bom: (.+) has no active BOM/.exec(msg)?.[1]
    out.push(t(hit[1], { product: product ?? '' }))
  }
  return [...new Set(out.filter(Boolean))]
}
