/** 仓储模块：向通用实体页面注册的 UI 扩展（各类单据行操作，领料单物料需求面板，来料 IQC）。 */
import type { MesRow } from '@/lib/api/mes/common'
import type { MesExtensions } from '@/features/mes/common/types'
import { DocActions } from './doc-actions'
import { IqcActions } from './iqc-actions'
import { IssueRequirement } from './issue-requirement'
import { ReceiptActions } from './receipt-actions'

/** 仓储模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  extraActions: {
    receipt: (r: MesRow) => <ReceiptActions row={r} />,
    material_issue: (r: MesRow) => (
      <DocActions
        row={r}
        entity='material_issue'
        path='material-issue'
        prefix='issue'
      />
    ),
    shipment: (r: MesRow) => (
      <DocActions row={r} entity='shipment' path='shipment' prefix='shipment' />
    ),
    material_receipt: (r: MesRow) => (
      <DocActions
        row={r}
        entity='material_receipt'
        path='material-receipt'
        prefix='inbound'
      />
    ),
    material_receipt_line: (r: MesRow) => <IqcActions row={r} />,
  },
  rowPanels: { material_issue: IssueRequirement },
}
