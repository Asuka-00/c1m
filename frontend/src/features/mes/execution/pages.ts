import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

/** Execution pages (menu component keys from the backend module menus). */
export const pages: Pages = {
  'mes-page:lot-console': lazy(() => import('./lot-console')),
  'mes-page:lot-trace': lazy(() => import('./lot-trace')),
}
