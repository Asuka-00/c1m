/** MES planning: work order transitions and lot start. */
import { http } from '../client'
import type { MesRow } from './common'

export interface StartPlanLot {
  lot_no: string
  qty: number
  slots: number[]
  wafer_ids: string[]
}
export interface StartPlan {
  work_order_id: string
  wo_status: string
  planned_qty: number
  started_qty: number
  max_qty: number
  remaining: number
  lot_size: number
  max_lot_size: number
  first_step_id: string | null
  first_step_seq: number | null
  site_id: string | null
  lots: StartPlanLot[]
}
export interface StartLotIn {
  qty: number
  carrier_id?: string | null
  slots?: number[]
  source_ref?: string | null
}

export const woApi = {
  transition: (id: string, action: string) =>
    http
      .post<MesRow>(`/mes/work-order/${id}/transition`, { action })
      .then((r) => r.data),
  plan: (id: string, body: { lot_size?: number; qty?: number }) =>
    http
      .post<StartPlan>(`/mes/work-order/${id}/start-plan`, body)
      .then((r) => r.data),
  start: (id: string, lots: StartLotIn[]) =>
    http
      .post<{ data: MesRow[] }>(`/mes/work-order/${id}/start`, { lots })
      .then((r) => r.data),
  undo: (id: string, lotIds?: string[]) =>
    http
      .post<{ undone: number }>(`/mes/work-order/${id}/undo-start`, {
        lot_ids: lotIds,
      })
      .then((r) => r.data),
}
