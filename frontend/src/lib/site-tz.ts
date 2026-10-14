/**
 * 站点时区与业务日期（D75）。
 *
 * 业务日期（到期日、报表默认日期等）一律按站点时区计算，不按浏览器时区，也不用
 * `toISOString().slice(0, 10)`（那是 UTC 日期；台北 00:00–08:00 时 UTC 还是前一天）。
 *
 * 站点时区来源（优先级从高到低）：
 * 1. 会话 / 租户信息里的 `site_tz`（D75，随 B6 交付；先预留读取位置）；
 * 2. 厂区列表：第一个启用厂区（按编码排序）的 `timezone`（与后端 `tenant_tz()` 一致），
 *    兼容 `tenant_tz` / `tz` 字段名；
 * 3. 默认 `Asia/Taipei`。
 */

export const DEFAULT_SITE_TZ = 'Asia/Taipei'

let current = DEFAULT_SITE_TZ
const listeners = new Set<() => void>()

/** 订阅站点时区变化（供 useSyncExternalStore 使用）。 */
export function subscribeSiteTz(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** 是否为浏览器认识的 IANA 时区。 */
export function isValidTz(tz: unknown): tz is string {
  if (typeof tz !== 'string' || !tz.trim()) return false
  try {
    new Intl.DateTimeFormat('en-CA', { timeZone: tz })
    return true
  } catch {
    return false
  }
}

/** 当前站点时区。 */
export const getSiteTz = (): string => current

/** 设置站点时区；无效值回落到 Asia/Taipei。返回实际生效的时区。 */
export function setSiteTz(tz: unknown): string {
  const next = isValidTz(tz) ? tz : DEFAULT_SITE_TZ
  if (next !== current) {
    current = next
    listeners.forEach((fn) => fn())
  }
  return current
}

const fmtCache = new Map<string, Intl.DateTimeFormat>()
const fmt = (tz: string) => {
  let f = fmtCache.get(tz)
  if (!f) {
    f = new Intl.DateTimeFormat('en-CA', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
    fmtCache.set(tz, f)
  }
  return f
}

/** 某个时刻在站点时区的日期 YYYY-MM-DD。 */
export function siteDate(
  at: Date | number | string = new Date(),
  tz: string = current
): string {
  const d = at instanceof Date ? at : new Date(at)
  const parts = fmt(isValidTz(tz) ? tz : DEFAULT_SITE_TZ).formatToParts(d)
  const get = (k: string) => parts.find((p) => p.type === k)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}`
}

/** 站点「今天」YYYY-MM-DD。 */
export const siteToday = (now: Date = new Date(), tz: string = current) =>
  siteDate(now, tz)

/** 日期字符串加减天数（纯日历运算，与时区无关）。 */
export function addDays(ymd: string, days: number): string {
  const [y, m, d] = ymd.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10)
}

/** 两个日期字符串相差的天数（b − a）。 */
export function diffDays(a: string, b: string): number {
  const ms = (s: string) => {
    const [y, m, d] = s.split('-').map(Number)
    return Date.UTC(y, m - 1, d)
  }
  return Math.round((ms(b) - ms(a)) / 86_400_000)
}

const HAS_ZONE = /(?:[zZ]|[+-]\d{2}:?\d{2})$/

/**
 * 接口返回的日期 / 时间转成站点日期：
 * - `YYYY-MM-DD`（或不带时区的本地时间）直接取前 10 位，视为站点日期；
 * - 带时区的时间（`...Z`、`+08:00`）换算到站点时区再取日期。
 */
export function toSiteDate(v: string, tz: string = current): string {
  const s = v.trim()
  if (s.length > 10 && HAS_ZONE.test(s)) return siteDate(new Date(s), tz)
  return s.slice(0, 10)
}

type SiteRow = Record<string, unknown>

/** 从会话 / 租户信息里读 `site_tz`（D75 / B6）；没有返回 null。 */
export function sessionSiteTz(...sources: unknown[]): string | null {
  for (const s of sources) {
    if (!s || typeof s !== 'object') continue
    const o = s as Record<string, unknown>
    if (isValidTz(o.site_tz)) return o.site_tz
    const tenant = o.tenant as Record<string, unknown> | undefined
    if (tenant && isValidTz(tenant.site_tz)) return tenant.site_tz
  }
  return null
}

/** 厂区列表里的时区：第一个启用厂区（按编码）；兼容 `timezone` / `tenant_tz` / `tz`。 */
export function siteListTz(rows: SiteRow[] | null | undefined): string | null {
  const active = (rows ?? [])
    .filter((r) => r.is_active !== false)
    .sort((a, b) => String(a.code ?? '').localeCompare(String(b.code ?? '')))
  for (const r of active) {
    for (const k of ['timezone', 'tenant_tz', 'tz', 'site_tz']) {
      if (isValidTz(r[k])) return r[k] as string
    }
  }
  return null
}

/** 按优先级解析站点时区：会话 site_tz > 厂区列表 > Asia/Taipei。 */
export function resolveSiteTz(
  session: unknown[],
  sites: SiteRow[] | null | undefined
): string {
  return sessionSiteTz(...session) ?? siteListTz(sites) ?? DEFAULT_SITE_TZ
}
