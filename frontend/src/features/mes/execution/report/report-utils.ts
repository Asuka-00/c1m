/** 报表工具函数：日期与百分比格式。 */

/** 本地日期 YYYY-MM-DD（偏移 ``days`` 天）。 */
export function isoDay(days = 0): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** 百分比显示（null 为 —）。 */
export const pct = (v: number | null) =>
  v === null ? '—' : `${(v * 100).toFixed(1)}%`
