/** 权限与平台角色接口。 */
import { del, get, patch, post, put, type ListQuery } from '../request'
import type { Message, Paged, Permission, Role } from '../types'

/** 权限 CRUD 接口。 */
export const permissionsApi = {
  list: (q: ListQuery) => get<Paged<Permission>>('/permissions/', q),
  create: (b: { code: string; description?: string; scope: string }) =>
    post<Permission>('/permissions/', b),
  update: (id: string, b: Partial<Permission>) =>
    patch<Permission>(`/permissions/${id}`, b),
  remove: (id: string) => del<Message>(`/permissions/${id}`),
}

/** 平台角色 CRUD 接口。 */
export const rolesApi = {
  list: (q: ListQuery) => get<Paged<Role>>('/roles/', q),
  create: (b: { name: string; description?: string | null }) =>
    post<Role>('/roles/', b),
  update: (id: string, b: { name?: string; description?: string | null }) =>
    patch<Role>(`/roles/${id}`, b),
  remove: (id: string) => del<Message>(`/roles/${id}`),
  setPermissions: (id: string, codes: string[]) =>
    put<Role>(`/roles/${id}/permissions`, { codes }),
}
