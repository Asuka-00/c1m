/** 租户、成员与租户角色接口。 */
import { del, get, patch, post, put, type ListQuery } from '../request'
import type {
  Member,
  Message,
  MyTenant,
  Paged,
  Permission,
  Role,
  Tenant,
} from '../types'

/** 当前用户可访问的租户。 */
export const myTenantsApi = {
  myTenants: () => get<Paged<MyTenant>>('/tenants/me'),
}

/** 租户、成员与租户角色管理接口。 */
export const tenantsApi = {
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
  /** 可授予租户角色的权限（仅租户作用域） */
  permissions: (id: string) =>
    get<Paged<Permission>>(`/tenants/${id}/permissions`),
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
}
