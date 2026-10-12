import { http } from './client'
import type {
  ConfigGroup,
  Member,
  PublicConfig,
  UploadedFile,
  Menu,
  Message,
  MyMenus,
  MyTenant,
  Paged,
  Permission,
  Role,
  Tenant,
  User,
} from './types'

const get = <T>(url: string, params?: object) =>
  http.get<T>(url, { params }).then((r) => r.data)
const post = <T>(url: string, body?: unknown) =>
  http.post<T>(url, body).then((r) => r.data)
const put = <T>(url: string, body?: unknown) =>
  http.put<T>(url, body).then((r) => r.data)
const patch = <T>(url: string, body?: unknown) =>
  http.patch<T>(url, body).then((r) => r.data)
const del = <T>(url: string) => http.delete<T>(url).then((r) => r.data)

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

export type UserIn = Partial<Omit<User, 'id' | 'created_at'>> & {
  password?: string
}

/** Typed API client for the FastAPI backend. */
export const api = {
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
  myMenus: () => get<MyMenus>('/menus/me'),
  config: {
    /** platform defaults (platform config:read) */
    platform: () => get<Paged<ConfigGroup>>('/config/groups'),
    updatePlatform: (code: string, values: Record<string, unknown>) =>
      patch<ConfigGroup>(`/config/groups/${code}`, { values }),
    /** current tenant (X-Tenant-ID): effective values + inheritance info */
    tenant: () => get<Paged<ConfigGroup>>('/tenants/current/config'),
    updateTenant: (code: string, values: Record<string, unknown>) =>
      patch<ConfigGroup>(`/tenants/current/config/${code}`, { values }),
    resetTenantItem: (code: string, item: string) =>
      del<ConfigGroup>(`/tenants/current/config/${code}/${item}`),
    /** unauthenticated branding; tenant slug optional */
    public: (tenant?: string) =>
      get<PublicConfig>('/config/public', tenant ? { tenant } : undefined),
  },
  files: {
    upload: (file: File, scope: 'tenant' | 'platform' = 'tenant') => {
      const fd = new FormData()
      fd.append('file', file)
      return http
        .post<UploadedFile>('/files/upload', fd, { params: { scope } })
        .then((r) => r.data)
    },
  },
  myTenants: () => get<Paged<MyTenant>>('/tenants/me'),

  users: {
    list: (q: ListQuery) => get<Paged<User>>('/users/', q),
    create: (b: UserIn) => post<User>('/users/', b),
    update: (id: string, b: UserIn) => patch<User>(`/users/${id}`, b),
    remove: (id: string) => del<Message>(`/users/${id}`),
    roles: (id: string) => get<Role[]>(`/users/${id}/roles`),
    addRole: (id: string, roleId: string) =>
      post<Role[]>(`/users/${id}/roles/${roleId}`),
    removeRole: (id: string, roleId: string) =>
      del<Role[]>(`/users/${id}/roles/${roleId}`),
  },
  permissions: {
    list: (q: ListQuery) => get<Paged<Permission>>('/permissions/', q),
    create: (b: { code: string; description?: string; scope: string }) =>
      post<Permission>('/permissions/', b),
    update: (id: string, b: Partial<Permission>) =>
      patch<Permission>(`/permissions/${id}`, b),
    remove: (id: string) => del<Message>(`/permissions/${id}`),
  },
  roles: {
    list: (q: ListQuery) => get<Paged<Role>>('/roles/', q),
    create: (b: { name: string; description?: string | null }) =>
      post<Role>('/roles/', b),
    update: (id: string, b: { name?: string; description?: string | null }) =>
      patch<Role>(`/roles/${id}`, b),
    remove: (id: string) => del<Message>(`/roles/${id}`),
    setPermissions: (id: string, codes: string[]) =>
      put<Role>(`/roles/${id}/permissions`, { codes }),
  },
  tenants: {
    list: (q: ListQuery) => get<Paged<Tenant>>('/tenants/', q),
    create: (b: { name: string; slug: string }) => post<Tenant>('/tenants/', b),
    update: (id: string, b: { name?: string; status?: string }) =>
      patch<Tenant>(`/tenants/${id}`, b),
    remove: (id: string) => del<Message>(`/tenants/${id}`),
    members: (id: string, q: ListQuery) =>
      get<Paged<Member>>(`/tenants/${id}/members`, q),
    addMember: (id: string, b: { email: string; roles: string[] }) =>
      post<Member>(`/tenants/${id}/members`, b),
    setMemberRoles: (id: string, userId: string, roles: string[]) =>
      put<Member>(`/tenants/${id}/members/${userId}/roles`, { roles }),
    removeMember: (id: string, userId: string) =>
      del<Message>(`/tenants/${id}/members/${userId}`),
    roles: (id: string, q: ListQuery) =>
      get<Paged<Role>>(`/tenants/${id}/roles`, q),
    createRole: (
      id: string,
      b: {
        name: string
        description?: string | null
        permission_codes?: string[]
      }
    ) => post<Role>(`/tenants/${id}/roles`, b),
    updateRole: (
      id: string,
      roleId: string,
      b: { name?: string; description?: string | null }
    ) => patch<Role>(`/tenants/${id}/roles/${roleId}`, b),
    removeRole: (id: string, roleId: string) =>
      del<Message>(`/tenants/${id}/roles/${roleId}`),
    setRolePermissions: (id: string, roleId: string, codes: string[]) =>
      put<Role>(`/tenants/${id}/roles/${roleId}/permissions`, { codes }),
  },
  menus: {
    list: (q: ListQuery) => get<Paged<Menu>>('/menus/', q),
    create: (b: Partial<Menu>) => post<Menu>('/menus/', b),
    update: (id: string, b: Partial<Menu>) => patch<Menu>(`/menus/${id}`, b),
    remove: (id: string) => del<Message>(`/menus/${id}`),
  },
}
export * from './types'
