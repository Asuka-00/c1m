/** MES 仓储：完工入库单与各类单据的状态迁移，批次可入库数量与工单物料需求。 */
import { http } from '../client'
import type { MesRow } from './common'

/** 批次的可入库数量。 */
export interface Receivable {
  lot_id: string
  qty: number
  received_qty: number
  pending_qty: number
  receivable_qty: number
  lot_status: string
}

/** 入库单接口：提交 / 退回 / 确认 / 取消，及批次可入库数量。 */
export const receiptApi = {
  transition: (id: string, action: string) =>
    http
      .post<MesRow>(`/mes/receipt/${id}/transition`, { action })
      .then((r) => r.data),
  receivable: (lotId: string) =>
    http
      .get<Receivable>(`/mes/receipt/receivable/${lotId}`)
      .then((r) => r.data),
}

/** 工单某种物料的需求与已领数量。 */
interface MaterialRequirement {
  material_id: string
  material: string | null
  uom: string | null
  required: number
  issued: number
  short: number
}

/** 工单物料需求（来自下达时锁定的 BOM）。 */
interface WoRequirements {
  work_order: string
  bom: string | null
  lines: MaterialRequirement[]
}

/** 仓储单据接口：领料单 / 出货单 / 来料接收单的确认 / 取消，及来料 IQC 判定。 */
export const docApi = {
  transition: (path: string, id: string, action: string) =>
    http
      .post<MesRow>(`/mes/${path}/${id}/transition`, { action })
      .then((r) => r.data),
  iqc: (lineId: string, result: string) =>
    http
      .post<MesRow>(`/mes/material-receipt/lines/${lineId}/iqc`, { result })
      .then((r) => r.data),
}

/** 领料单接口：工单物料需求。 */
export const issueApi = {
  requirements: (woId: string) =>
    http
      .get<WoRequirements>(`/mes/material-issue/requirements/${woId}`)
      .then((r) => r.data),
}
