/** Platform user administration. */
import { del, get, patch, post, type ListQuery } from '../request'
import type { Message, Paged, Role, User } from '../types'

export type UserIn = Partial<Omit<User, 'id' | 'created_at'>> & {
  password?: string
}

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
