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
