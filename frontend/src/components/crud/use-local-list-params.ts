import { useState } from 'react'
import { DEFAULT_PAGE_SIZE, type ListParams } from './use-list-params'

/** 与 useListParams() 约定相同，但状态保存在组件内（用于
 *  嵌在对话框 / 抽屉中的表格，此时 URL 属于所在页面）。 */
export function useLocalListParams(
  initialPageSize = DEFAULT_PAGE_SIZE
): ListParams {
  const [s, setS] = useState({
    page: 1,
    pageSize: initialPageSize,
    sortBy: undefined as string | undefined,
    sortOrder: 'asc' as 'asc' | 'desc',
    filters: {} as Record<string, string>,
  })
  return {
    ...s,
    q: s.filters.q ?? '',
    setFilter: (name, value) =>
      setS((p) => {
        const filters = { ...p.filters }
        if (value == null || value === '') delete filters[name]
        else filters[name] = value
        return { ...p, filters, page: 1 }
      }),
    query: {
      page: s.page,
      page_size: s.pageSize,
      ...(s.sortBy ? { sort_by: s.sortBy, sort_order: s.sortOrder } : {}),
      ...s.filters,
    },
    set: (patch) => setS((p) => ({ ...p, ...patch })),
  }
}
