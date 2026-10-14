/**
 * a72b85b（D77 补充三 / D83）：查询参数里的日期与时间。
 * - datetime（holds date_from/to、eqp/alarms from/to、map imported_from/to、通用列表 datetime 等值与 _from/_to）
 *   必须带时区偏移（按 site_tz）；不带时区后端 422 timezone_required。
 * - date 字段（11 个，见 STRICT_DATE_FIELDS）以及 shift-logs、ct-move 的 date_from/to 只发严格 YYYY-MM-DD。
 * - mock 校验：date 不合格式 → 422 value_error ctx.reason=pattern；datetime 不带时区 → 422 timezone_required
 *   （type 本身，无 ctx.reason）；datetime 无法解析 → 422 value_error ctx.reason=pattern。loc 均为 ["query", 字段名]。
 */
import { getSiteTz, siteDayBoundary, siteWallToIso } from '@/lib/site-tz'
import type { MesEntity } from './mes/common'
import { apiError } from './mes/mock-utils'

/** 只收严格 YYYY-MM-DD 的 date 字段（实体.字段）。 */
export const STRICT_DATE_FIELDS = [
  'calendar_day.day',
  'equipment_capability.qualified_until',
  'material_lot.expiry_date',
  'operator_qual.certified_on',
  'operator_qual.expires_on',
  'product_route.effective_from',
  'product_route.effective_to',
  'shift_log.shift_date',
  'tool.expiry_date',
  'work_order.planned_start',
  'work_order.due_date',
] as const

export const YMD = /^\d{4}-\d{2}-\d{2}$/
const OFFSET = /(Z|[+-]\d{2}:\d{2})$/i
const LEADING_YMD = /^\d{4}-\d{2}-\d{2}/

/** date：带时间 / 偏移的值截到日期部分；其他原样（交给后端 / mock 报 pattern）。 */
export function strictDate(v: string | undefined): string | undefined {
  if (v == null || v === '') return undefined
  const s = v.trim()
  return LEADING_YMD.test(s) ? s.slice(0, 10) : s
}

/**
 * datetime：已带偏移原样；只有日期 → 站点当天 0 点（end=true 为次日 0 点，半开区间 D77）；
 * 无偏移墙上时间 → 按站点时区补偏移；无法识别的原样（交给后端报错）。
 */
export function offsetDatetime(
  v: string | undefined,
  end = false,
  tz: string = getSiteTz()
): string | undefined {
  if (v == null || v === '') return undefined
  const s = v.trim()
  if (OFFSET.test(s)) return s
  if (YMD.test(s)) {
    if (!end) return siteDayBoundary(s, false, tz)
    const [y, m, d] = s.split('-').map(Number)
    const next = new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10)
    return siteDayBoundary(next, false, tz)
  }
  return siteWallToIso(s, tz) ?? s
}

type Kind = 'date' | 'datetime'
const fieldOf = (key: string) => key.replace(/_(from|to)$/, '')

/** 通用列表查询：按实体字段类型归一 date / datetime 的等值和 _from/_to 参数。 */
export function normalizeListQuery<T extends Record<string, unknown>>(
  e: Pick<MesEntity, 'code' | 'fields'> | undefined,
  query: T
): T {
  if (!e) return query
  const out: Record<string, unknown> = { ...query }
  for (const [k, v] of Object.entries(query)) {
    if (typeof v !== 'string' || !v) continue
    const base = fieldOf(k)
    const f = e.fields.find((x) => x.column === base || x.name === base)
    if (!f) continue
    if (f.type === 'date') out[k] = strictDate(v)
    else if (f.type === 'datetime')
      out[k] = offsetDatetime(v, k.endsWith('_to') && YMD.test(v.trim()))
  }
  return out as T
}

/** mock 校验一组查询参数（顺序同后端：逐个字段，先格式后范围由调用方处理）。 */
export function mockQueryDateCheck(
  query: Record<string, unknown>,
  kinds: Record<string, Kind>
) {
  for (const [k, kind] of Object.entries(kinds)) {
    const v = query[k]
    if (v == null || v === '') continue
    const s = String(v)
    if (kind === 'date') {
      if (!YMD.test(s)) return patternErr(k, s)
      continue
    }
    const naive = s.replace(OFFSET, '')
    const parsable =
      /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?)?$/.test(naive) &&
      !Number.isNaN(
        Date.parse(`${naive.length === 10 ? `${naive}T00:00` : naive}Z`)
      )
    if (!parsable) return patternErr(k, s)
    if (!OFFSET.test(s))
      return apiError(422, [
        {
          loc: ['query', k],
          type: 'timezone_required',
          code: 'timezone_required',
          msg: `${k}: timezone offset required (Z or +hh:mm)`,
          input: s,
        },
      ])
  }
  return null
}

const patternErr = (k: string, s: string) =>
  apiError(422, [
    {
      loc: ['query', k],
      type: 'value_error',
      code: 'value_error',
      msg: `${k}: invalid date / datetime`,
      ctx: { reason: 'pattern' },
      input: s,
    },
  ])
