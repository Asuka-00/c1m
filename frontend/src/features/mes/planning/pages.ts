/** 计划模块页面注册。 */
import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

/** 计划模块页面（菜单组件 key 来自后端模块菜单）。 */
export const pages: Pages = {
  'mes-page:lot-start': lazy(() => import('./lot-start')),
  'mes-page:wo-board': lazy(() => import('./wo-board')),
}
