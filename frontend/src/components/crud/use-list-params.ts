import { useNavigate, useSearch } from '@tanstack/react-router'
import type { ListQuery } from '@/lib/api'
import { DEFAULT_FILTERS, type FilterDef } from './filter-defs'

/** 默认每页条数（与后端默认值一致）。 */
export const DEFAULT_PAGE_SIZE = 20

type Patch = Partial<{
  page: number
  pageSize: number
  sortBy: string | undefined
  sortOrder: 'asc' | 'desc'
}>

/** useListParams 的返回值：分页、排序、筛选状态及其更新函数。 */
export interface ListParams {
  page: number
  pageSize: number
  sortBy?: string
  sortOrder: 'asc' | 'desc'
  /** 自由文本搜索（?q=），无则为 '' */
  q: string
  /** URL 中的当前筛选值，按筛选名索引（含 q） */
  filters: Record<string, string>
  /** 设置一个筛选（回到第 1 页）；'' / undefined 表示移除 */
  setFilter: (name: string, value: string | undefined) => void
  /** 传给 API 客户端的查询参数 */
  query: ListQuery
  set: (patch: Patch) => void
}

/** 保存在 URL 中的分页 + 排序 + 筛选状态
 *  （?page=&pageSize=&sortBy=&sortOrder=&q=&<filter>=）。传入与 DataTable 相同的筛选定义
 *  （默认：一个 `q` 关键字搜索）。
 *  默认：第 1 页、每页 20 条、后端默认排序。 */
export function useListParams(
  filterDefs: FilterDef[] = DEFAULT_FILTERS
): ListParams {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const navigate = useNavigate()
  const page = Math.max(1, Number(search.page) || 1)
  const pageSize = Number(search.pageSize) || DEFAULT_PAGE_SIZE
  const sortBy = typeof search.sortBy === 'string' ? search.sortBy : undefined
  const sortOrder = search.sortOrder === 'desc' ? 'desc' : 'asc'
  const filters: Record<string, string> = {}
  for (const { name } of filterDefs) {
    const v = search[name] == null ? '' : String(search[name]).trim()
    if (v) filters[name] = v
  }
  const update = (fn: (next: Record<string, unknown>) => void) =>
    navigate({
      to: '.',
      replace: true,
      search: ((prev: Record<string, unknown>) => {
        const next: Record<string, unknown> = { ...prev }
        fn(next)
        if (next.page === 1) delete next.page
        if (next.pageSize === DEFAULT_PAGE_SIZE) delete next.pageSize
        if (!next.sortBy) {
          delete next.sortBy
          delete next.sortOrder
        }
        return next
      }) as never,
    })
  return {
    page,
    pageSize,
    sortBy,
    sortOrder,
    q: filters.q ?? '',
    filters,
    setFilter: (name, value) =>
      update((next) => {
        delete next.page
        if (value == null || value === '') delete next[name]
        // 布尔值按布尔存储，使 URL 为 ?is_active=false 而非 ?is_active=%22false%22
        else
          next[name] =
            value === 'true' ? true : value === 'false' ? false : value
      }),
    query: {
      page,
      page_size: pageSize,
      ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder } : {}),
      ...filters,
    },
    set: (patch) => update((next) => Object.assign(next, patch)),
  }
}
