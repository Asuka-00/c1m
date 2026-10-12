/** 设备接口（状态看板、E10 手动改状态、PM）。 */
import { http } from '../client'

/** PM 计划到期状态。 */
export interface PmStatus {
  plan_id: string
  plan: string
  last_done: string | null
  next_due: string | null
  days_left: number | null
  lots_since: number
  interval_lots: number | null
  due: boolean
  warn: boolean
}

/** 看板中的 E10 状态。 */
export interface BoardState {
  id: string
  code: string
  name: string
  category: string
  color: string | null
}

/** 设备状态看板行。 */
export interface BoardRow {
  id: string
  code: string
  name: string
  is_active: boolean
  state: BoardState | null
  next: {
    id: string
    code: string
    name: string
    reason_required: boolean
  }[]
  pm: PmStatus[]
  pm_due: boolean
  pm_warn: boolean
  down: boolean
}

/** 设备接口客户端。 */
export const eqpApi = {
  board: () =>
    http.get<{ data: BoardRow[] }>('/mes/eqp/board').then((r) => r.data.data),
  changeE10: (
    id: string,
    body: { to_state_id: string; reason_id?: string; comment?: string }
  ) => http.post(`/mes/eqp/${id}/e10`, body).then((r) => r.data),
  pmComplete: (
    planId: string,
    body: { equipment_id: string; result: 'ok' | 'ng'; comment?: string }
  ) => http.post(`/mes/eqp/pm/${planId}/complete`, body).then((r) => r.data),
}
