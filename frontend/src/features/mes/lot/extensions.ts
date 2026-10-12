import type { MesExtensions } from '@/features/mes/common/types'
import { LotDetail } from './lot-detail'
import { LotTypePreview } from './lot-type-preview'

/** Lot module UI extensions. */
export const extensions: MesExtensions = {
  rowPanels: { lot_type: LotTypePreview, lot: LotDetail },
}
