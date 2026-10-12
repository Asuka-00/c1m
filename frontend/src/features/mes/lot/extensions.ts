/** 批次模块：向通用实体页面注册的 UI 扩展（批次详情、批次类型预览）。 */
import type { MesExtensions } from '@/features/mes/common/types'
import { LotDetail } from './lot-detail'
import { LotTypePreview } from './lot-type-preview'

/** 批次模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  rowPanels: { lot_type: LotTypePreview, lot: LotDetail },
}
