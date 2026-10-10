import type { MesRow } from '@/lib/api/mes'
import { CodeRulePreview } from './code-rule-preview'
import { LotTypePreview } from './lot-type-preview'
import { RouteEditor } from './route-editor'
import { UomConverter } from './uom-converter'

/** Entity-specific detail panels (first tab of the row detail sheet). */
export const ROW_PANELS: Record<
  string,
  React.ComponentType<{ row: MesRow }>
> = {
  code_rule: CodeRulePreview,
  uom: UomConverter,
  route: RouteEditor,
  lot_type: LotTypePreview,
}

/** Entity-specific extra row action buttons. */
export const EXTRA_ACTIONS: Record<string, (r: MesRow) => React.ReactNode> = {}
