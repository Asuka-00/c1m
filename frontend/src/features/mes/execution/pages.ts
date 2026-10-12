/** 执行模块页面注册。 */
import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

/** 执行模块页面（菜单组件 key 来自后端模块菜单）。 */
export const pages: Pages = {
  'mes-page:lot-console': lazy(() => import('./lot-console')),
  'mes-page:qtime-monitor': lazy(() => import('./qtime-monitor')),
  'mes-page:lot-trace': lazy(() => import('./lot-trace')),
}
