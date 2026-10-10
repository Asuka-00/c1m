import { lazy, type ComponentType, type LazyExoticComponent } from 'react'

/**
 * Component keys the backend menu registry may reference (menu.component).
 * Routes exist ONLY if GET /menus/me returns a node with that path + key.
 */
export const COMPONENTS: Record<string, LazyExoticComponent<ComponentType>> = {
  dashboard: lazy(() => import('@/features/dashboard')),
  users: lazy(() => import('@/features/users')),
  roles: lazy(() => import('@/features/roles')),
  'tenant-roles': lazy(() => import('@/features/roles/tenant-roles')),
  permissions: lazy(() => import('@/features/permissions')),
  tenants: lazy(() => import('@/features/tenants')),
  members: lazy(() => import('@/features/members')),
  menus: lazy(() => import('@/features/menus')),
  settings: lazy(() => import('@/features/settings')),
  config: lazy(() => import('@/features/config')),
  'mes-page:lot-start': lazy(() => import('@/features/mes/lot-start')),
}
