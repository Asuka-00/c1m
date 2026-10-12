/** Shared request helpers and list-query types for the domain API clients. */
import { http } from './client'

export const get = <T>(url: string, params?: object) =>
  http.get<T>(url, { params }).then((r) => r.data)
export const post = <T>(url: string, body?: unknown) =>
  http.post<T>(url, body).then((r) => r.data)
export const put = <T>(url: string, body?: unknown) =>
  http.put<T>(url, body).then((r) => r.data)
export const patch = <T>(url: string, body?: unknown) =>
  http.patch<T>(url, body).then((r) => r.data)
export const del = <T>(url: string) => http.delete<T>(url).then((r) => r.data)

/** Server-side pagination/sorting params (backend default page_size 20, max 100). */
export interface ListQuery {
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  /** case-insensitive search over the endpoint's text fields */
  q?: string
  /** endpoint-specific filters (role_id, is_active, status, scope, …) */
  [filter: string]: string | number | boolean | undefined
}
/** For option lists / small reference data: one max-size page. */
export const ALL: ListQuery = { page_size: 100 }
