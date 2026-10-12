import { lazy } from 'react'
import { pages as mes } from '@/features/mes/pages'
import { pages as platform } from '@/features/platform/pages'
import type { Pages } from './types'

/**
 * Component keys the backend menu registry may reference (menu.component).
 * Routes exist ONLY if GET /menus/me returns a node with that path + key.
 */
export const COMPONENTS: Pages = {
  dashboard: lazy(() => import('@/features/shell/dashboard')),
  ...platform,
  ...mes,
}
