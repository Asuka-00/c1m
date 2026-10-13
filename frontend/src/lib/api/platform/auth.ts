/** 登录与当前用户接口。 */
import { http } from '../client'
import { get, patch } from '../request'
import type { Message, User } from '../types'

/** 认证接口：登录、当前用户、注册与密码找回。 */
export const authApi = {
  login: (username: string, password: string) =>
    http
      .post<{
        access_token: string
      }>('/login/access-token', new URLSearchParams({ username, password }), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      .then((r) => r.data),
  me: () => get<User>('/users/me'),
  updateMe: (body: { full_name?: string | null; email?: string | null }) =>
    patch<User>('/users/me', body),
  updatePassword: (body: { current_password: string; new_password: string }) =>
    patch<Message>('/users/me/password', body),
}
