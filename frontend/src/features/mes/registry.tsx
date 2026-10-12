import { extensions as common } from './common/extensions'
import type { MesExtensions } from './common/types'
import { extensions as execution } from './execution/extensions'
import { extensions as lot } from './lot/extensions'
import { extensions as planning } from './planning/extensions'
import { extensions as process } from './process/extensions'
import { extensions as product } from './product/extensions'

/**
 * Composition root of the MES UI modules (mirrors backend app/modules.py):
 * every domain contributes entity-specific panels/actions to the generic
 * entity pages. Domains without custom UI (factory, equipment, quality) are
 * rendered entirely from the backend specs.
 */
const MODULES: MesExtensions[] = [
  common,
  product,
  process,
  lot,
  planning,
  execution,
]

/** Entity-specific detail panels (first tab of the row detail sheet). */
export const ROW_PANELS = Object.assign(
  {},
  ...MODULES.map((m) => m.rowPanels ?? {})
) as NonNullable<MesExtensions['rowPanels']>

/** Entity-specific extra row action buttons. */
export const EXTRA_ACTIONS = Object.assign(
  {},
  ...MODULES.map((m) => m.extraActions ?? {})
) as NonNullable<MesExtensions['extraActions']>
