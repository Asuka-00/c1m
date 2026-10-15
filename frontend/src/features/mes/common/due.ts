/**
 * 距今天数（按本地日期计算，负数表示已过）。
 *
 * @param ymd 日期（YYYY-MM-DD，可带时间部分）
 * @param today 基准日（默认今天）
 */
export function daysUntil(ymd: string, today = new Date()): number {
  const [y, m, d] = ymd.slice(0, 10).split('-').map(Number)
  const a = Date.UTC(y, m - 1, d)
  const b = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((a - b) / 86_400_000)
}
