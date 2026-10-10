import type { MesRow } from '@/lib/api/mes'
import { CodeRulePreview } from './code-rule-preview'

/** Entity-specific detail panels (first tab of the row detail sheet). */
export const ROW_PANELS: Record<
  string,
  React.ComponentType<{ row: MesRow }>
> = {
  code_rule: CodeRulePreview,
}

/** Entity-specific extra row action buttons. */
export const EXTRA_ACTIONS: Record<string, (r: MesRow) => React.ReactNode> = {}
