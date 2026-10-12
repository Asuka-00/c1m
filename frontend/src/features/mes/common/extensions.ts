/** MES 公共模块：向通用实体页面注册的 UI 扩展。 */
import { CodeRulePreview } from './code-rule-preview'
import type { MesExtensions } from './types'

/** 公共模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  rowPanels: { code_rule: CodeRulePreview },
}
