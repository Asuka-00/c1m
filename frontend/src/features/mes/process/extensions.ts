/** 工艺模块：向通用实体页面注册的 UI 扩展（路线流程图、工程变更操作）。 */
import { createElement } from 'react'
import type { MesRow } from '@/lib/api/mes/common'
import type { MesExtensions } from '@/features/mes/common/types'
import { ChangeActions, ChangeResult } from './change-actions'
import { RouteFlow } from './route-flow'

/** 工艺模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  rowPanels: { route: RouteFlow, change_order: ChangeResult },
  extraActions: {
    change_order: (r: MesRow) => createElement(ChangeActions, { row: r }),
  },
}
