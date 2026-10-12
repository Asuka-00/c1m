/** 产品模块：向通用实体页面注册的 UI 扩展（单位换算）。 */
import type { MesExtensions } from '@/features/mes/common/types'
import { UomConverter } from './uom-converter'

/** 产品模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  rowPanels: { uom: UomConverter },
}
