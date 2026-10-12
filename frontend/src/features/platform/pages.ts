/** 平台页面注册。 */
import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

/** 平台页面（菜单组件 key 来自后端菜单注册表）。 */
export const pages: Pages = {
  users: lazy(() => import('./users')),
  roles: lazy(() => import('./rbac/roles')),
  'tenant-roles': lazy(() => import('./rbac/roles/tenant-roles')),
  permissions: lazy(() => import('./rbac/permissions')),
  tenants: lazy(() => import('./tenants')),
  members: lazy(() => import('./tenants/members')),
  menus: lazy(() => import('./menus')),
  settings: lazy(() => import('./settings')),
  config: lazy(() => import('./config')),
  notifications: lazy(() => import('./notifications')),
  'notify-subscriptions': lazy(() => import('./notifications/subscriptions')),
}
