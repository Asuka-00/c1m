/**
 * 距今天数（按本地日期计算，负数表示已过）。
 *
 * @param ymd 日期（YYYY-MM-DD）或带时区的时间（如 UTC `...Z`，先换算成本地日期）
 * @param today 基准日（默认今天）
 */
export function daysUntil(ymd: string, today = new Date()): number {
  let y: number, m: number, d: number
  if (ymd.length > 10) {
    const t = new Date(ymd)
    ;[y, m, d] = [t.getFullYear(), t.getMonth() + 1, t.getDate()]
  } else [y, m, d] = ymd.split('-').map(Number)
  const a = Date.UTC(y, m - 1, d)
  const b = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((a - b) / 86_400_000)
}
