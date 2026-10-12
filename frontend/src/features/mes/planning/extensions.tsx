/** 计划模块：向通用实体页面注册的 UI 扩展（工单行操作、开批进度）。 */
import type { MesRow } from '@/lib/api/mes/common'
import type { MesExtensions } from '@/features/mes/common/types'
import { WoActions } from './wo-actions'

/** 计划模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  extraActions: { work_order: (r: MesRow) => <WoActions row={r} /> },
}
