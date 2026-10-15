/** 打标模块页面注册（P3-F4；后端菜单未导出，组件 key 为前端假设）。 */
import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

export const pages: Pages = {
  'mes-page:marking-template': lazy(() => import('./template-page')),
  'mes-page:marking': lazy(() => import('./job-page')),
}
