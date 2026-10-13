/** 权限与平台角色接口。 */
import { del, get, patch, post, put, type ListQuery } from '../request'
import type { Message, Paged, Permission, Role } from '../types'

/** 权限 CRUD 接口。 */
export const permissionsApi = {
  list: (q: ListQuery) => get<Paged<Permission>>('/platform/permissions/', q),
  create: (b: { code: string; description?: string; scope: string }) =>
    post<Permission>('/platform/permissions/', b),
  update: (id: string, b: Partial<Permission>) =>
    patch<Permission>(`/platform/permissions/${id}`, b),
  remove: (id: string) => del<Message>(`/platform/permissions/${id}`),
}

/** 平台角色 CRUD 接口。 */
export const rolesApi = {
  list: (q: ListQuery) => get<Paged<Role>>('/platform/roles/', q),
  create: (b: { name: string; description?: string | null }) =>
    post<Role>('/platform/roles/', b),
  update: (id: string, b: { name?: string; description?: string | null }) =>
    patch<Role>(`/platform/roles/${id}`, b),
  remove: (id: string) => del<Message>(`/platform/roles/${id}`),
  setPermissions: (id: string, codes: string[]) =>
    put<Role>(`/platform/roles/${id}/permissions`, { codes }),
}
