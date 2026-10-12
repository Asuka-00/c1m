/** 执行模块：向通用实体页面注册的 UI 扩展（批次行操作、Hold 释放、工具寿命）。 */
import type { MesRow } from '@/lib/api/mes/common'
import type { MesExtensions } from '@/features/mes/common/types'
import { HoldActions, LotActions } from './exec-actions'

/** 执行模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  extraActions: {
    lot: (r: MesRow) => <LotActions row={r} />,
    lot_hold: (r: MesRow) => <HoldActions row={r} />,
  },
}
