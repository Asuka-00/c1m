/** Login and current-user endpoints. */
import { http } from '../client'
import { get, patch } from '../request'
import type { Message, User } from '../types'

export const authApi = {
  login: (email: string, password: string) =>
    http
      .post<{
        access_token: string
      }>(
        '/login/access-token',
        new URLSearchParams({ username: email, password }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
      )
      .then((r) => r.data),
  me: () => get<User>('/users/me'),
  updateMe: (body: { full_name?: string | null; email?: string }) =>
    patch<User>('/users/me', body),
  updatePassword: (body: { current_password: string; new_password: string }) =>
    patch<Message>('/users/me/password', body),
}
