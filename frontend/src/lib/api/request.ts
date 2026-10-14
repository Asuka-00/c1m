/** 各业务域 API 客户端共享的请求工具与列表查询类型。 */
import { http } from './client'

/** GET 请求，返回响应数据。 */
export const get = <T>(url: string, params?: object) =>
  http.get<T>(url, { params }).then((r) => r.data)
/** POST 请求，返回响应数据。 */
export const post = <T>(url: string, body?: unknown) =>
  http.post<T>(url, body).then((r) => r.data)
/** PUT 请求，返回响应数据。 */
export const put = <T>(url: string, body?: unknown) =>
  http.put<T>(url, body).then((r) => r.data)
/** PATCH 请求，返回响应数据。 */
export const patch = <T>(url: string, body?: unknown) =>
  http.patch<T>(url, body).then((r) => r.data)
/** DELETE 请求，返回响应数据。 */
export const del = <T>(url: string) => http.delete<T>(url).then((r) => r.data)

/** 服务端分页 / 排序参数（后端默认 page_size 20，最大 100）。 */
export interface ListQuery {
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  /** 在接口的文本字段上做不区分大小写的搜索 */
  q?: string
  /** 接口专用筛选条件（role_id、is_active、status、scope 等） */
  [filter: string]: string | number | boolean | undefined
}
/** 用于选项列表 / 小型参考数据：取一页最大条数。 */
export const ALL: ListQuery = { page_size: 100 }

/** 后端分页上限（core/pagination.py MAX_PAGE_SIZE）。 */
export const MAX_PAGE_SIZE = 100

/**
 * 按 `page_size=100` 逐页拉全（后端 page_size 上限 100，超出 422）。
 * `fetchPage(page)` 返回 `{data, count}`；拉满 `count` 或某页为空即停止，最多 `maxPages` 页。
 */
export async function fetchAllPages<T>(
  fetchPage: (
    page: number,
    page_size: number
  ) => Promise<{ data: T[]; count: number }>,
  maxPages = 50
): Promise<T[]> {
  const out: T[] = []
  for (let page = 1; page <= maxPages; page++) {
    const r = await fetchPage(page, MAX_PAGE_SIZE)
    out.push(...r.data)
    if (
      !r.data.length ||
      out.length >= r.count ||
      r.data.length < MAX_PAGE_SIZE
    )
      break
  }
  return out
}
