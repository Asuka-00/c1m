/** 工艺模块：向通用实体页面注册的 UI 扩展（路线流程图）。 */
import type { MesExtensions } from '@/features/mes/common/types'
import { RouteFlow } from './route-flow'

/** 工艺模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  rowPanels: { route: RouteFlow },
}
