/** 光罩模块页面注册（P3）。 */
import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

export const pages: Pages = {
  'mes-page:reticle': lazy(() => import('./reticle-page')),
}
