import { CodeRulePreview } from './code-rule-preview'
import type { MesExtensions } from './types'

/** Common module UI extensions. */
export const extensions: MesExtensions = {
  rowPanels: { code_rule: CodeRulePreview },
}
