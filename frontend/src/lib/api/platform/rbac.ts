/** 权限与平台角色接口。 */
import { del, get, patch, post, put, type ListQuery } from '../request'
import type { Message, Paged, Permission, PermNode, Role } from '../types'

/** 权限 CRUD 接口。 */
export const permissionsApi = {
  list: (q: ListQuery) => get<Paged<Permission>>('/platform/permissions/', q),
  create: (b: Partial<Permission> & { code: string; scope: string }) =>
    post<Permission>('/platform/permissions/', b),
  update: (id: string, b: Partial<Permission>) =>
    patch<Permission>(`/platform/permissions/${id}`, b),
  remove: (id: string) => del<Message>(`/platform/permissions/${id}`),
  /** 统一权限树（菜单 + 权限）；space: all / workspace / platform，scope 过滤权限作用域 */
  tree: (q?: { space?: string; scope?: string }) =>
    get<PermNode[]>('/platform/permission-tree', q),
}

/** 角色写入请求体。 */
interface RoleIn {
  name?: string
  title?: string | null
  description?: string | null
  status?: string
  permission_codes?: string[]
}

/** 平台角色 CRUD 接口。 */
export const rolesApi = {
  list: (q: ListQuery) => get<Paged<Role>>('/platform/roles/', q),
  create: (b: RoleIn & { name: string }) => post<Role>('/platform/roles/', b),
  update: (id: string, b: RoleIn) => patch<Role>(`/platform/roles/${id}`, b),
  remove: (id: string) => del<Message>(`/platform/roles/${id}`),
  setPermissions: (id: string, codes: string[]) =>
    put<Role>(`/platform/roles/${id}/permissions`, { codes }),
}
