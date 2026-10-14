/** 坐标图列表筛选 → 请求参数（日期按站点时区 0 点带偏移发送，结束日含当天：to = 次日 0 点）。 */
import type { MapListParams } from '@/lib/api/mes/map'
import { addDays, getSiteTz } from '@/lib/site-tz'
import { rangeInverted, rangeParam } from '@/components/crud/filter-defs'

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

/**
 * `YYYY-MM-DD`（站点日期）→ 当天站点 0 点（带偏移，D75）；`plusDays` 用于结束日（次日 0 点）。
 * 与通用 CRUD 的 `rangeParam`（D77 半开区间）同一实现。
 */
export function localDayStart(
  d: string,
  plusDays = 0,
  tz: string = getSiteTz()
): string | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return undefined
  return rangeParam(addDays(d, plusDays - 1), true, 'datetime', tz)
}

export function mapListParams(f: MapListFilter): MapListParams {
  // D77 补充一：倒置区间不发导入时间范围
  const inv = rangeInverted(f.from, f.to)
  return {
    page: f.page,
    page_size: MAP_PAGE_SIZE,
    sort_by: 'imported_at',
    sort_order: 'desc',
    ...(f.q.trim() ? { q: f.q.trim() } : {}),
    ...(f.substrate.trim() ? { substrate_id: f.substrate.trim() } : {}),
    ...(f.latestOnly ? { latest_only: true } : {}),
    ...(!inv && localDayStart(f.from)
      ? { imported_from: localDayStart(f.from) }
      : {}),
    ...(!inv && localDayStart(f.to, 1)
      ? { imported_to: localDayStart(f.to, 1) }
      : {}),
  }
}
