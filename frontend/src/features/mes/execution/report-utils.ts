/** 报表工具函数：日期与百分比格式。 */
import { addDays, getSiteTz, siteToday } from '@/lib/site-tz'

/** 站点日期 YYYY-MM-DD（D75：按站点时区的今天，偏移 ``days`` 天）。 */
export function isoDay(
  days = 0,
  now: Date = new Date(),
  tz: string = getSiteTz()
): string {
  return addDays(siteToday(now, tz), days)
}

/** 百分比显示（null 为 —）。 */
export const pct = (v: number | null) =>
  v === null ? '—' : `${(v * 100).toFixed(1)}%`
