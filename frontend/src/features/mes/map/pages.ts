/** 坐标图模块页面注册（P1 / F1）。 */
import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

/** 菜单组件 key 暂定 `mes-page:map-import`，等后端 B4 菜单定下后对齐。 */
export const pages: Pages = {
  'mes-page:map-import': lazy(() => import('./map-import')),
}
