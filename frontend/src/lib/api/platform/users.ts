/** 平台用户管理接口。 */
import { del, get, patch, post, put, type ListQuery } from '../request'
import type { Message, Paged, Role, User, UserTenantRoles } from '../types'

/** 新增 / 更新用户的请求体。 */
export type UserIn = Partial<Omit<User, 'id' | 'created_at' | 'role_names'>> & {
  password?: string
}

/** 用户管理接口（平台空间 /platform/users，仅超级用户）。 */
export const usersApi = {
  list: (q: ListQuery) => get<Paged<User>>('/platform/users/', q),
  create: (b: UserIn) => post<User>('/platform/users/', b),
  update: (id: string, b: UserIn) => patch<User>(`/platform/users/${id}`, b),
  remove: (id: string) => del<Message>(`/platform/users/${id}`),
  roles: (id: string) => get<Role[]>(`/platform/users/${id}/roles`),
  /** 整体设置用户的平台角色 */
  setRoles: (id: string, roleIds: string[]) =>
    put<Role[]>(`/platform/users/${id}/roles`, { role_ids: roleIds }),
  /** 用户所属租户及租户角色 */
  tenants: (id: string) =>
    get<UserTenantRoles[]>(`/platform/users/${id}/tenants`),
  /** 整体设置用户的租户成员身份与租户角色 */
  setTenants: (id: string, items: UserTenantRoles[]) =>
    put<UserTenantRoles[]>(`/platform/users/${id}/tenants`, { items }),
}
