import type { ComponentType, ReactNode } from 'react'
import type { MesRow } from '@/lib/api/mes/common'

/** What a MES domain module contributes to the generic entity pages. */
export interface MesExtensions {
  /** entity code -> detail panel (first tab of the row detail sheet) */
  rowPanels?: Record<string, ComponentType<{ row: MesRow }>>
  /** entity code -> extra row action buttons */
  extraActions?: Record<string, (r: MesRow) => ReactNode>
}
