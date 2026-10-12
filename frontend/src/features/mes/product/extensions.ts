import type { MesExtensions } from '@/features/mes/common/types'
import { UomConverter } from './uom-converter'

/** Product module UI extensions. */
export const extensions: MesExtensions = {
  rowPanels: { uom: UomConverter },
}
