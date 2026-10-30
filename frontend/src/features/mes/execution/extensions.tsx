/** 执行模块：向通用实体页面注册的 UI 扩展（批次行操作、NCR 登记与审批、工具寿命）。 */
import type { MesRow } from '@/lib/api/mes/common'
import type { MesExtensions } from '@/features/mes/common/types'
import { LotActions } from './exec-actions'
import { NcrPanel, RaiseNcr } from './semi/ncr'

/** 执行模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  extraActions: {
    lot: (r: MesRow) => (
      <>
        <LotActions row={r} />
        <RaiseNcr row={r} />
      </>
    ),
  },
  rowPanels: { ncr: NcrPanel },
}
