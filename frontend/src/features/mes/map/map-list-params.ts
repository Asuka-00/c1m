/** 坐标图列表筛选 → 请求参数（日期按本地时区换成 UTC，结束日含当天：to = 次日 0 点）。 */
import type { MapListParams } from '@/lib/api/mes/map'

export interface MapListFilter {
  q: string
  substrate: string
  latestOnly: boolean
  from: string
  to: string
  page: number
}

export const MAP_PAGE_SIZE = 20

export const emptyMapFilter = (): MapListFilter => ({
  q: '',
  substrate: '',
  latestOnly: false,
  from: '',
  to: '',
  page: 1,
})

/** `YYYY-MM-DD`（本地日期）→ 当天本地 0 点的 UTC ISO 字符串；`plusDays` 用于结束日。 */
export function localDayStart(d: string, plusDays = 0): string | undefined {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(d)
  if (!m) return undefined
  const x = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + plusDays)
  return x.toISOString()
}

export function mapListParams(f: MapListFilter): MapListParams {
  return {
    page: f.page,
    page_size: MAP_PAGE_SIZE,
    sort_by: 'imported_at',
    sort_order: 'desc',
    ...(f.q.trim() ? { q: f.q.trim() } : {}),
    ...(f.substrate.trim() ? { substrate_id: f.substrate.trim() } : {}),
    ...(f.latestOnly ? { latest_only: true } : {}),
    ...(localDayStart(f.from) ? { imported_from: localDayStart(f.from) } : {}),
    ...(localDayStart(f.to, 1) ? { imported_to: localDayStart(f.to, 1) } : {}),
  }
}
