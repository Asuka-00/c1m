/** 仓储模块：向通用实体页面注册的 UI 扩展（入库单行操作）。 */
import type { MesRow } from '@/lib/api/mes/common'
import type { MesExtensions } from '@/features/mes/common/types'
import { ReceiptActions } from './receipt-actions'

/** 仓储模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  extraActions: { receipt: (r: MesRow) => <ReceiptActions row={r} /> },
}
