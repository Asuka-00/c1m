import type { MesExtensions } from '@/features/mes/common/types'
import { RouteFlow } from './route-flow'

/** Process module UI extensions. */
export const extensions: MesExtensions = {
  rowPanels: { route: RouteFlow },
}
