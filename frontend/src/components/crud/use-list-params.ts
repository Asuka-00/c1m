import { useNavigate, useSearch } from '@tanstack/react-router'
import type { ListQuery } from '@/lib/api'
import {
  DEFAULT_FILTERS,
  filterKeys,
  rangeParam,
  type FilterDef,
} from './filter-defs'

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
  /** 同时设置两个筛选（日期范围起止，回到第 1 页） */
  setRange: (ka: string, a: string, kb: string, b: string) => void
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
  // id：从关联对象链接跳转而来时按指定记录过滤（任何列表页通用）
  for (const name of ['id', ...filterDefs.flatMap(filterKeys)]) {
    const v = search[name] == null ? '' : String(search[name]).trim()
    if (v) filters[name] = v
  }
  const query: Record<string, string> = { ...filters }
  for (const d of filterDefs)
    if (d.type === 'daterange')
      filterKeys(d).forEach((k, i) => {
        if (filters[k]) query[k] = rangeParam(filters[k], i === 1, d.kind)
      })
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
    setRange: (ka, a, kb, b) =>
      update((next) => {
        delete next.page
        for (const [k, v] of [
          [ka, a],
          [kb, b],
        ])
          if (v) next[k] = v
          else delete next[k]
      }),
    query: {
      page,
      page_size: pageSize,
      ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder } : {}),
      ...query,
    },
    set: (patch) => update((next) => Object.assign(next, patch)),
  }
}
