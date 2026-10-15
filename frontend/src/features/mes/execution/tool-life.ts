/**
 * 工具 / 耗材寿命（P2-B10 / F9，D54-5 修订）：
 * - 已用 >= 上限：进站 409 check_blocked，检查项 tool_life，overridable=false（红）；
 * - 上限 × warn_ratio <= 已用 < 上限：预警区间，进站 200，警告写入检查记录和履历（黄）。
 * 数量是定点字符串（numeric(18,6)），显示与比较都走 lib/decimal。
 */
import { t } from '@/i18n'
import type { CheckResult, ExecContext } from '@/lib/api/mes/execution'
import { decimalGreater, decimalText } from '@/lib/decimal'
import { enumLabel } from '@/features/mes/common/labels'

export type ToolLifeLevel = 'ok' | 'warn' | 'over'

const has = (v: unknown) => v != null && v !== ''

/** 比例文本 → 数字；不在 (0, 1] 内为 null。 */
const ratioOf = (v: unknown) => {
  if (!has(v)) return null
  const r = Number(decimalText(v as string))
  return r > 0 && r <= 1 ? r : null
}

/**
 * 预警比例：后端有效值 effective_warn_ratio（23c502d，工具 → 类型 → warn_pct/100）→
 * 工具 warn_ratio → warn_pct / 100 → 0.9。
 */
export function warnRatio(row: Record<string, unknown>): number {
  const r = ratioOf(row.effective_warn_ratio) ?? ratioOf(row.warn_ratio)
  if (r != null) return r
  const p = Number(row.warn_pct)
  return has(row.warn_pct) && p > 0 ? p / 100 : 0.9
}

/** 寿命上限：effective_max_usage（含工具类型的上限）→ max_usage；没有为 null。 */
export function maxUsage(row: Record<string, unknown>): string | null {
  const v = has(row.effective_max_usage)
    ? row.effective_max_usage
    : row.max_usage
  return has(v) ? decimalText(v as string) : null
}

/** 寿命等级；没有上限为 null。 */
export function toolLifeLevel(
  used: unknown,
  max: unknown,
  ratio: number
): ToolLifeLevel | null {
  const u = decimalText(used as string) || '0'
  const m = decimalText(max as string)
  if (!m || m === '0' || m.startsWith('-')) return null
  if (u.startsWith('-')) return 'ok'
  if (!decimalGreater(m, u)) return 'over'
  return Number(u) >= Number(m) * ratio ? 'warn' : 'ok'
}

const NUM = String.raw`([\d.eE+-]+)`
const RULES: [RegExp, (m: RegExpExecArray) => string][] = [
  [
    new RegExp(String.raw`^tool (\S+) reached its life \(${NUM}/${NUM}\)$`),
    (m) =>
      t('mes.toolLife.reached', {
        tool: m[1],
        used: decimalText(m[2]),
        max: decimalText(m[3]),
      }),
  ],
  [
    new RegExp(String.raw`^tool (\S+) near end of life \(${NUM}/${NUM}\)$`),
    (m) =>
      t('mes.toolLife.near', {
        tool: m[1],
        used: decimalText(m[2]),
        max: decimalText(m[3]),
      }),
  ],
  [
    /^tool (\S+) expired on (\S+)$/,
    (m) => t('mes.toolLife.expired', { tool: m[1], date: m[2] }),
  ],
  [
    /^tool (\S+) expires on (\S+)$/,
    (m) => t('mes.toolLife.expiring', { tool: m[1], date: m[2] }),
  ],
  [
    /^tool (\S+) is (\S+)$/,
    (m) =>
      t('mes.toolLife.status', { tool: m[1], status: toolStatusText(m[2]) }),
  ],
]

/** 工具状态三语；未登记的状态码不原样显示（P2-D4）。 */
export function toolStatusText(code: string): string {
  const v = enumLabel('tool_status', code)
  return v === code ? t('mes.toolLife.unknownStatus') : v
}

/** tool_life 检查说明的本地化（多条以 "; " 分隔）；不认识的部分保留原文。 */
export function toolLifeMessage(r: CheckResult): string {
  // P2-D4：用量 >= 上限时优先显示“已达寿命上限（用量/上限）”，即使后端给的是状态类说明
  const dt = r.data ?? {}
  if (r.result !== 'warn' && has(dt.usage) && has(dt.max)) {
    const used = decimalText(dt.usage as string)
    const max = decimalText(dt.max as string)
    if (toolLifeLevel(used, max, 1) === 'over')
      return t('mes.toolLife.reached', {
        tool: String(dt.tool ?? ''),
        used,
        max,
      })
  }
  return r.message
    .split('; ')
    .map((part) => {
      for (const [re, f] of RULES) {
        const m = re.exec(part)
        if (m) return f(m)
      }
      return part
    })
    .join('；')
}

/** 进站成功（200）时预警区间的 tool_life 提示；没有则为 null。 */
export function toolLifeWarning(results: CheckResult[] | undefined) {
  const w = (results ?? []).filter(
    (r) => r.check_type === 'tool_life' && r.result === 'warn'
  )
  if (!w.length) return null
  return `${w.map(toolLifeMessage).join('；')} · ${t('mes.toolLife.logged')}`
}

/**
 * 给 tool_life 检查结果补上进站上下文里的用量 / 上限（按 data.tool_id 或 tool 编码匹配），
 * 供说明优先显示“已达寿命上限”。
 */
export function withToolUsage(
  results: CheckResult[],
  cx: Pick<ExecContext, 'tools'>
): CheckResult[] {
  const opts = (cx.tools ?? []).flatMap((g) => g.options)
  return results.map((r) => {
    if (r.check_type !== 'tool_life' || !r.data) return r
    const o = opts.find(
      (x) =>
        x.id === r.data?.tool_id || (r.data?.tool && x.code === r.data.tool)
    )
    if (!o || r.data.usage != null) return r
    return { ...r, data: { ...r.data, usage: o.usage, max: o.max } }
  })
}
