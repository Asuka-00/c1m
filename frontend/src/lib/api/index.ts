import { authApi } from './platform/auth'
import { configApi } from './platform/config'
import { platformApi } from './platform/console'
import { filesApi } from './platform/files'
import { menusApi, myMenusApi } from './platform/menus'
import { notificationsApi } from './platform/notifications'
import { permissionsApi, rolesApi } from './platform/rbac'
import { myTenantsApi, tenantsApi } from './platform/tenants'
import { usersApi } from './platform/users'

/**
 * FastAPI 后端的类型化 API 客户端，由各业务域客户端
 * lib/api/platform/* 组合而成（MES 客户端位于 lib/api/mes/*）。
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
  notifications: notificationsApi,
  platform: platformApi,
}
export { ALL, type ListQuery } from './request'
export type { UserIn } from './platform/users'
export type * from './platform/notifications'
export * from './types'
