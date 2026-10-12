import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

/** Planning pages (menu component keys from the backend module menus). */
export const pages: Pages = {
  'mes-page:lot-start': lazy(() => import('./lot-start')),
}
