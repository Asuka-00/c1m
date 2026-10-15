/**
 * 站点时区与业务日期（D75）。
 *
 * 业务日期（到期日、报表默认日期等）一律按站点时区计算，不按浏览器时区，也不用
 * `toISOString().slice(0, 10)`（那是 UTC 日期；台北 00:00–08:00 时 UTC 还是前一天）。
 *
 * 站点时区来源（优先级从高到低）：
 * 1. `/tenants/me` 的 `tenant.site_tz`（D75，随 B6 交付）；会话 / 菜单顶层 `site_tz` 作备用；
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

/**
 * 从会话 / 租户信息里读 `site_tz`（D75 / B6）；没有返回 null。
 * 优先 `/tenants/me` 的 `tenant.site_tz`，其次各来源顶层的 `site_tz`（备用）。
 */
export function sessionSiteTz(...sources: unknown[]): string | null {
  const objs = sources.filter(
    (s): s is Record<string, unknown> => !!s && typeof s === 'object'
  )
  for (const o of objs) {
    const tenant = o.tenant as Record<string, unknown> | undefined
    if (tenant && isValidTz(tenant.site_tz)) return tenant.site_tz
  }
  for (const o of objs) if (isValidTz(o.site_tz)) return o.site_tz
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

const offFmtCache = new Map<string, Intl.DateTimeFormat>()

/** 某时刻在时区 tz 的 UTC 偏移（分钟，东正西负），含夏令时。 */
export function tzOffsetMinutes(at: number, tz: string): number {
  let f = offFmtCache.get(tz)
  if (!f) {
    f = new Intl.DateTimeFormat('en-CA', {
      timeZone: tz,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    offFmtCache.set(tz, f)
  }
  const p = Object.fromEntries(
    f.formatToParts(new Date(at)).map((x) => [x.type, x.value])
  )
  const wall = Date.UTC(
    +p.year,
    +p.month - 1,
    +p.day,
    +p.hour,
    +p.minute,
    +p.second
  )
  return Math.round((wall - Math.floor(at / 1000) * 1000) / 60_000)
}

/** 站点时区的墙上时间（按 UTC 字段给出的毫秒）→ 该时刻所用的偏移（Intl 反算，两次收敛）。 */
function offsetAtWall(wall: number, tz: string): number {
  let off = tzOffsetMinutes(wall, tz)
  for (let i = 0; i < 2; i++) {
    const next = tzOffsetMinutes(wall - off * 60_000, tz)
    if (next === off) break
    off = next
  }
  return off
}

const fmtOffset = (min: number) => {
  const s = min < 0 ? '-' : '+'
  const a = Math.abs(min)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${s}${p(Math.floor(a / 60))}:${p(a % 60)}`
}

/**
 * D82：站点墙上时间（`YYYY-MM-DDTHH:mm` 或带秒）→ 带偏移 ISO（如 `2026-10-15T08:30:00+08:00`）。
 * 时区非法时用 Asia/Taipei；格式不对返回 null。
 */
export function siteWallToIso(
  local: string,
  tz: string = current
): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(
    local.trim()
  )
  if (!m) return null
  const zone = isValidTz(tz) ? tz : DEFAULT_SITE_TZ
  const [y, mo, d, h, mi, se] = m.slice(1).map((x) => Number(x ?? 0))
  const wall = Date.UTC(y, mo - 1, d, h, mi, se)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${m[1]}-${m[2]}-${m[3]}T${p(h)}:${p(mi)}:${p(se)}${fmtOffset(offsetAtWall(wall, zone))}`
}

/**
 * 站点日期的当天边界（D75，带偏移，后端不换算时区、两头都含）：
 * 开始 `YYYY-MM-DDT00:00:00+HH:MM`，结束 `YYYY-MM-DDT23:59:59.999999+HH:MM`。
 * 偏移按当天该时刻的实际偏移算（夏令时切换日开始和结束的偏移可以不同）。
 */
export function siteDayBoundary(
  ymd: string,
  end: boolean,
  tz: string = current
): string {
  const zone = isValidTz(tz) ? tz : DEFAULT_SITE_TZ
  const [y, m, d] = ymd.split('-').map(Number)
  const wall = end
    ? Date.UTC(y, m - 1, d, 23, 59, 59)
    : Date.UTC(y, m - 1, d, 0, 0, 0)
  const time = end ? '23:59:59.999999' : '00:00:00'
  return `${ymd.slice(0, 10)}T${time}${fmtOffset(offsetAtWall(wall, zone))}`
}
