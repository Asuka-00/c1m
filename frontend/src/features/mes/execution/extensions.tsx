import type { MesRow } from '@/lib/api/mes/common'
import type { MesExtensions } from '@/features/mes/common/types'
import { HoldActions, LotActions } from './exec-actions'

/** Execution module UI extensions. */
export const extensions: MesExtensions = {
  extraActions: {
    lot: (r: MesRow) => <LotActions row={r} />,
    lot_hold: (r: MesRow) => <HoldActions row={r} />,
  },
}
