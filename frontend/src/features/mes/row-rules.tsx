import type { MesRow } from '@/lib/api/mes'
import { WoProgress } from './wo-actions'

/** Entity-specific cell renderers: entity -> field -> cell. */
export const CELLS: Record<
  string,
  Record<string, (r: MesRow) => React.ReactNode>
> = {
  work_order: { started_qty: (r) => <WoProgress row={r} /> },
}

/** Entity-specific edit / delete rules (on top of permissions + versioning). */
export const ROW_RULES: Record<
  string,
  { edit?: (r: MesRow) => boolean; remove?: (r: MesRow) => boolean }
> = {
  work_order: {
    edit: (r) => !['closed', 'cancelled'].includes(String(r.wo_status)),
    remove: (r) => r.wo_status === 'draft',
  },
}
