/** 租户、成员与租户角色接口。 */
import { del, get, patch, post, put, type ListQuery } from '../request'
import type {
  Member,
  Message,
  MyTenant,
  Paged,
  PermNode,
  Role,
  Tenant,
} from '../types'

/** 租户内新建 / 修改成员账号的请求体。 */
export interface MemberUserIn {
  full_name?: string | null
  email?: string | null
  password?: string
  roles?: string[]
  is_active?: boolean
}

/** 当前用户可访问的租户。 */
export const myTenantsApi = {
  myTenants: () => get<Paged<MyTenant>>('/tenants/me'),
}

/** 租户、成员与租户角色管理接口。 */
export const tenantsApi = {
  update: (id: string, b: { name?: string; status?: string }) =>
    patch<Tenant>(`/tenants/${id}`, b),
  remove: (id: string) => del<Message>(`/tenants/${id}`),
  members: (id: string, q: ListQuery) =>
    get<Paged<Member>>(`/tenants/${id}/members`, q),
  /** 按用户名添加已有用户 */
  addMember: (id: string, b: { username: string; roles: string[] }) =>
    post<Member>(`/tenants/${id}/members`, b),
  /** 在租户内直接创建新用户（不能创建超级用户） */
  createUser: (id: string, b: MemberUserIn & { username: string }) =>
    post<Member>(`/tenants/${id}/members/new`, b),
  /** 修改成员账号（仅只属于本租户的用户；含重置密码） */
  updateUser: (id: string, userId: string, b: MemberUserIn) =>
    patch<Member>(`/tenants/${id}/members/${userId}/user`, b),
  setMemberRoles: (id: string, userId: string, roles: string[]) =>
    put<Member>(`/tenants/${id}/members/${userId}/roles`, { roles }),
  removeMember: (id: string, userId: string) =>
    del<Message>(`/tenants/${id}/members/${userId}`),
  /** 可授予租户角色的权限树（仅租户作用域） */
  permissionTree: (id: string) =>
    get<PermNode[]>(`/tenants/${id}/permission-tree`),
  roles: (id: string, q: ListQuery) =>
    get<Paged<Role>>(`/tenants/${id}/roles`, q),
  createRole: (
    id: string,
    b: {
      name: string
      title?: string | null
      description?: string | null
      status?: string
      permission_codes?: string[]
    }
  ) => post<Role>(`/tenants/${id}/roles`, b),
  updateRole: (
    id: string,
    roleId: string,
    b: {
      name?: string
      title?: string | null
      description?: string | null
      status?: string
    }
  ) => patch<Role>(`/tenants/${id}/roles/${roleId}`, b),
  removeRole: (id: string, roleId: string) =>
    del<Message>(`/tenants/${id}/roles/${roleId}`),
  setRolePermissions: (id: string, roleId: string, codes: string[]) =>
    put<Role>(`/tenants/${id}/roles/${roleId}/permissions`, { codes }),
}
