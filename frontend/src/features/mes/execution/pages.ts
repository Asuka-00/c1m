/** 执行模块页面注册。 */
import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

/** 执行模块页面（菜单组件 key 来自后端模块菜单）。 */
export const pages: Pages = {
  'mes-page:lot-console': lazy(() => import('./lot-console')),
  'mes-page:qtime-monitor': lazy(() => import('./hold/qtime-monitor')),
  'mes-page:hold': lazy(() => import('./hold/hold-manage')),
  'mes-page:wip-dashboard': lazy(() => import('./report/wip-dashboard')),
  'mes-page:oee-report': lazy(() => import('./report/oee-report')),
  'mes-page:yield-report': lazy(() => import('./report/yield-report')),
  'mes-page:trace': lazy(() => import('./trace/trace')),
  'mes-page:lot-trace': lazy(() => import('./trace/lot-trace')),
  'mes-page:batch-ops': lazy(() => import('./dispatch/batch-ops')),
  'mes-page:shift-handover': lazy(() => import('./report/shift-handover')),
  'mes-page:label-print': lazy(() => import('./label/label-print')),
  'mes-page:carrier-ops': lazy(() => import('./carrier/carrier-ops')),
}
