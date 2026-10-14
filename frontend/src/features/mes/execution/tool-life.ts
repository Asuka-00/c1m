/**
 * 工具 / 耗材寿命（P2-B10 / F9，D54-5 修订）：
 * - 已用 >= 上限：进站 409 check_blocked，检查项 tool_life，overridable=false（红）；
 * - 上限 × warn_ratio <= 已用 < 上限：预警区间，进站 200，警告写入检查记录和履历（黄）。
 * 数量是定点字符串（numeric(18,6)），显示与比较都走 lib/decimal。
 */
import { t } from '@/i18n'
import type { CheckResult } from '@/lib/api/mes/execution'
import { decimalGreater, decimalText } from '@/lib/decimal'

export type ToolLifeLevel = 'ok' | 'warn' | 'over'

/** 预警比例：工具 warn_ratio → warn_pct / 100 → 0.9。 */
export function warnRatio(row: Record<string, unknown>): number {
  const r = Number(row.warn_ratio)
  if (row.warn_ratio != null && row.warn_ratio !== '' && r > 0 && r <= 1)
    return r
  const p = Number(row.warn_pct)
  return row.warn_pct != null && p > 0 ? p / 100 : 0.9
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
    (m) => t('mes.toolLife.status', { tool: m[1], status: m[2] }),
  ],
]

/** tool_life 检查说明的本地化（多条以 "; " 分隔）；不认识的部分保留原文。 */
export function toolLifeMessage(r: CheckResult): string {
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
