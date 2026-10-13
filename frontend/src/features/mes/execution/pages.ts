/** 执行模块页面注册。 */
import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

/** 执行模块页面（菜单组件 key 来自后端模块菜单）。 */
export const pages: Pages = {
  'mes-page:lot-console': lazy(() => import('./lot-console')),
  'mes-page:qtime-monitor': lazy(() => import('./qtime-monitor')),
  'mes-page:hold': lazy(() => import('./hold-manage')),
  'mes-page:wip-dashboard': lazy(() => import('./wip-dashboard')),
  'mes-page:oee-report': lazy(() => import('./oee-report')),
  'mes-page:yield-report': lazy(() => import('./yield-report')),
  'mes-page:trace': lazy(() => import('./trace')),
  'mes-page:lot-trace': lazy(() => import('./lot-trace')),
  'mes-page:batch-ops': lazy(() => import('./batch-ops')),
  'mes-page:shift-handover': lazy(() => import('./shift-handover')),
  'mes-page:carrier-ops': lazy(() => import('./carrier-ops')),
}
