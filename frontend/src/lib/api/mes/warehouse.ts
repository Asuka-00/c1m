/** MES 仓储：完工入库单状态迁移与批次可入库数量。 */
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
