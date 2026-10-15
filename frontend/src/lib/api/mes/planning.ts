/** MES 计划：工单状态迁移与开批。 */
import { http } from '../client'
import type { MesRow } from './common'

/** 开批计划中的一个批次（预览的批次号与晶圆号）。 */
export interface StartPlanLot {
  lot_no: string
  qty: number
  slots: number[]
  wafer_ids: string[]
}
/** 开批计划（不占用任何资源）。 */
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
/** 开批请求中的一个批次。 */
export interface StartLotIn {
  qty: number
  carrier_id?: string | null
  slots?: number[]
  source_ref?: string | null
}

/** 交期状态。 */
export type WoRisk = 'overdue' | 'at_risk' | 'ok' | 'none' | 'done'
/** 工单进度看板行。 */
export interface WoBoardRow {
  id: string
  code: string
  product: string | null
  status: string
  planned: number
  started: number
  completed: number
  wip: number
  scrapped: number
  lots: number
  progress: number
  due_date: string | null
  days_left: number | null
  risk: WoRisk
  wip_by_op: { operation: string; qty: number }[]
}

/** 工单接口：进度看板、状态迁移、开批计划、开批与撤销开批。 */
export const woApi = {
  board: (warnDays?: number) =>
    http
      .get<{ data: WoBoardRow[] }>('/mes/work-order/board', {
        params: { warn_days: warnDays },
      })
      .then((r) => r.data.data),
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
