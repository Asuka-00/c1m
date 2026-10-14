/** 坐标图模块页面注册（P1 / F1）。 */
import { lazy } from 'react'
import type { Pages } from '@/features/shell/dynamic/types'

/**
 * 菜单 `mes-map-import` → 组件 `mes-page:map-import`，权限 `mes.map:import`（FE-F1-1）。
 * 菜单项由后端 `mes/map/menus.py` 下发；前端已备好三语标题 `menu.mes-map-import`。
 */
export const pages: Pages = {
  'mes-page:map-import': lazy(() => import('./map-import')),
}
