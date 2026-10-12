import { lazy } from 'react'
import { pages as mes } from '@/features/mes/pages'
import { pages as platform } from '@/features/platform/pages'
import type { Pages } from './types'

/**
 * 后端菜单注册表可引用的组件 key（menu.component）。
 * 只有 GET /menus/me 返回了对应路径 + key 的节点时，路由才存在。
 */
export const COMPONENTS: Pages = {
  dashboard: lazy(() => import('@/features/shell/dashboard')),
  ...platform,
  ...mes,
}
