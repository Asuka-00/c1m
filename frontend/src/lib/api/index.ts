import { authApi } from './platform/auth'
import { configApi } from './platform/config'
import { filesApi } from './platform/files'
import { menusApi, myMenusApi } from './platform/menus'
import { permissionsApi, rolesApi } from './platform/rbac'
import { myTenantsApi, tenantsApi } from './platform/tenants'
import { usersApi } from './platform/users'

/**
 * Typed API client for the FastAPI backend, composed from the per-domain
 * clients in lib/api/platform/* (MES clients live in lib/api/mes/*).
 */
export const api = {
  ...authApi,
  ...myMenusApi,
  ...myTenantsApi,
  config: configApi,
  files: filesApi,
  users: usersApi,
  permissions: permissionsApi,
  roles: rolesApi,
  tenants: tenantsApi,
  menus: menusApi,
}
export { ALL, type ListQuery } from './request'
export type { UserIn } from './platform/users'
export * from './types'
