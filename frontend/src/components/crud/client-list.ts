import type { ListParams } from './use-list-params'

/** 客户端列表选项（数据一次性取回、量小且需实时刷新的看板 / 监控页）。 */
export interface ClientListOptions<T> {
  /** 关键字搜索（filters.q）匹配的文本 */
  text?: (row: T) => string
  /** 各筛选的匹配规则；未声明的筛选按 `String(row[name]) === value` 比较 */
  match?: Record<string, (row: T, value: string) => boolean>
}

/**
 * 在客户端对已取回的行做 关键字 / 筛选 / 排序 / 分页，约定与服务端列表一致。
 *
 * @param rows 全部行
 * @param p 列表参数（useListParams / useLocalListParams）
 * @param opts 搜索与筛选规则
 * @returns 当前页的行与筛选后的总数
 */
export function clientList<T>(
  rows: T[],
  p: ListParams,
  opts: ClientListOptions<T> = {}
): { rows: T[]; total: number } {
  const q = (p.filters.q ?? '').trim().toLowerCase()
  let out = rows.filter((r) => {
    if (q && !(opts.text?.(r) ?? '').toLowerCase().includes(q)) return false
    for (const [k, v] of Object.entries(p.filters)) {
      if (k === 'q' || v === '') continue
      const m = opts.match?.[k]
      const ok = m
        ? m(r, v)
        : String((r as Record<string, unknown>)[k] ?? '') === v
      if (!ok) return false
    }
    return true
  })
  if (p.sortBy) {
    const key = p.sortBy
    const dir = p.sortOrder === 'desc' ? -1 : 1
    out = [...out].sort((a, b) => {
      const x = (a as Record<string, unknown>)[key]
      const y = (b as Record<string, unknown>)[key]
      if (x == null) return y == null ? 0 : 1
      if (y == null) return -1
      return (x < y ? -1 : x > y ? 1 : 0) * dir
    })
  }
  const start = (p.page - 1) * p.pageSize
  return { rows: out.slice(start, start + p.pageSize), total: out.length }
}
