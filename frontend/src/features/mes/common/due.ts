import { diffDays, getSiteTz, siteToday, toSiteDate } from '@/lib/site-tz'

/**
 * 距站点今天的天数（D75：按站点时区，不按浏览器时区；负数表示已过）。
 *
 * @param ymd 日期（YYYY-MM-DD）或带时区的时间（如 UTC `...Z`，先换算成站点日期）
 * @param today 基准时刻（默认现在；取它在站点时区的日期）
 * @param tz 站点时区（默认当前站点时区）
 */
export function daysUntil(
  ymd: string,
  today: Date = new Date(),
  tz: string = getSiteTz()
): number {
  return diffDays(siteToday(today, tz), toSiteDate(ymd, tz))
}
