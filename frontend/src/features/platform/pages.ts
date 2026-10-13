/** 平台页面注册。 */
import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

/** 平台页面（菜单组件 key 来自后端菜单注册表）。
 *  工作区：成员 / 租户角色 / 角色权限 / 租户设置 / 通知；
 *  平台管理控制台（/platform/...）：租户、平台用户 / 角色 / 权限树、菜单、平台默认配置、渠道与日志。 */
export const pages: Pages = {
  // ---- 工作区 ----
  members: lazy(() => import('./tenants/members')),
  'tenant-roles': lazy(() => import('./rbac/roles/tenant-roles')),
  'tenant-role-permissions': lazy(() => import('./rbac/permissions/tenant')),
  settings: lazy(() => import('./settings')),
  config: lazy(() => import('./config')),
  notifications: lazy(() => import('./notifications')),
  'notify-subscriptions': lazy(() => import('./notifications/subscriptions')),
  // ---- 平台管理控制台 ----
  'platform-tenants': lazy(() => import('./console/tenants')),
  users: lazy(() => import('./users')),
  roles: lazy(() => import('./rbac/roles')),
  'platform-permissions': lazy(() => import('./rbac/permissions/platform')),
  menus: lazy(() => import('./menus')),
  'platform-config': lazy(() => import('./config/platform')),
  'notify-channels': lazy(() => import('./console/channels')),
  'platform-audit': lazy(() => import('./console/audit')),
  'login-log': lazy(() => import('./console/login-log')),
  'platform-ops-log': lazy(() => import('./console/ops-log')),
}
