import type { MesRow } from '@/lib/api/mes/common'
import type { MesExtensions } from '@/features/mes/common/types'
import { WoActions } from './wo-actions'

/** Planning module UI extensions. */
export const extensions: MesExtensions = {
  extraActions: { work_order: (r: MesRow) => <WoActions row={r} /> },
}
