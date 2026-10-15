/** MES 交接班日志接口。 */
import { http } from '../client'

/** 交接班日志行。 */
export interface ShiftLog {
  id: string
  shift_date: string
  shift: string | null
  shift_name: string | null
  area: string | null
  summary: string
  open_items: string | null
  handed_by: string | null
  handed_at: string | null
  log_status: 'open' | 'acknowledged'
  received_by: string | null
  received_at: string | null
  receive_comment: string | null
}

/** 交班请求。 */
export interface ShiftLogIn {
  shift_date: string
  shift_id: string
  area_id?: string
  summary: string
  open_items?: string
}

/** 交接班日志：列表、交班、接班确认。 */
export const shiftLogApi = {
  list: (p: { date_from?: string; date_to?: string }) =>
    http
      .get<{ data: ShiftLog[] }>('/mes/exec/shift-logs', { params: p })
      .then((r) => r.data.data),
  create: (body: ShiftLogIn) =>
    http.post<ShiftLog>('/mes/exec/shift-logs', body).then((r) => r.data),
  ack: (id: string, comment?: string) =>
    http
      .post<ShiftLog>(`/mes/exec/shift-logs/${id}/ack`, { comment })
      .then((r) => r.data),
}
