/** 平台用户管理接口。 */
import { del, get, patch, post, type ListQuery } from '../request'
import type { Message, Paged, Role, User } from '../types'

/** 新增 / 更新用户的请求体。 */
export type UserIn = Partial<Omit<User, 'id' | 'created_at'>> & {
  password?: string
}

/** 用户管理接口。 */
export const usersApi = {
  list: (q: ListQuery) => get<Paged<User>>('/users/', q),
  create: (b: UserIn) => post<User>('/users/', b),
  update: (id: string, b: UserIn) => patch<User>(`/users/${id}`, b),
  remove: (id: string) => del<Message>(`/users/${id}`),
  roles: (id: string) => get<Role[]>(`/users/${id}/roles`),
  addRole: (id: string, roleId: string) =>
    post<Role[]>(`/users/${id}/roles/${roleId}`),
  removeRole: (id: string, roleId: string) =>
    del<Role[]>(`/users/${id}/roles/${roleId}`),
}
