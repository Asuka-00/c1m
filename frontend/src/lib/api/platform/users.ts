/** 平台用户管理接口。 */
import { del, get, patch, post, type ListQuery } from '../request'
import type { Message, Paged, Role, User } from '../types'

/** 新增 / 更新用户的请求体。 */
export type UserIn = Partial<Omit<User, 'id' | 'created_at'>> & {
  password?: string
}

/** 用户管理接口（平台空间 /platform/users，仅超级用户）。 */
export const usersApi = {
  list: (q: ListQuery) => get<Paged<User>>('/platform/users/', q),
  create: (b: UserIn) => post<User>('/platform/users/', b),
  update: (id: string, b: UserIn) => patch<User>(`/platform/users/${id}`, b),
  remove: (id: string) => del<Message>(`/platform/users/${id}`),
  roles: (id: string) => get<Role[]>(`/platform/users/${id}/roles`),
  addRole: (id: string, roleId: string) =>
    post<Role[]>(`/platform/users/${id}/roles/${roleId}`),
  removeRole: (id: string, roleId: string) =>
    del<Role[]>(`/platform/users/${id}/roles/${roleId}`),
}
