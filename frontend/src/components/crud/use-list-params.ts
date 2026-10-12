import { useNavigate, useSearch } from '@tanstack/react-router'
import type { ListQuery } from '@/lib/api'
import { DEFAULT_FILTERS, type FilterDef } from './filter-defs'

export const DEFAULT_PAGE_SIZE = 20

type Patch = Partial<{
  page: number
  pageSize: number
  sortBy: string | undefined
  sortOrder: 'asc' | 'desc'
}>

export interface ListParams {
  page: number
  pageSize: number
  sortBy?: string
  sortOrder: 'asc' | 'desc'
  /** free-text search (?q=), '' when none */
  q: string
  /** current filter values from the URL, by filter name (incl. q) */
  filters: Record<string, string>
  /** set one filter (resets to page 1); '' / undefined removes it */
  setFilter: (name: string, value: string | undefined) => void
  /** query params for the API client */
  query: ListQuery
  set: (patch: Patch) => void
}

/** Pagination + sorting + filter state kept in the URL
 *  (?page=&pageSize=&sortBy=&sortOrder=&q=&<filter>=). Pass the same filter defs
 *  you give the DataTable (default: one `q` keyword search).
 *  Default: page 1, 20 rows, backend default sort. */
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
        // store booleans as such so the URL reads ?is_active=false, not ?is_active=%22false%22
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
