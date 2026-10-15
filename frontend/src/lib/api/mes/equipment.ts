/** 设备接口（状态看板、E10 手动改状态、PM）。 */
import { http } from '../client'
import { BODY_KEYS, pickBody } from '../request-body'

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

/** 可改 E10 状态的设备单元（主设备或腔体）。 */
export interface E10Unit {
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
}

/** 设备状态看板行。 */
export interface BoardRow extends E10Unit {
  workcenter: string | null
  workcenter_name: string | null
  /** 腔体及其 E10 状态 */
  chambers: E10Unit[]
  pm: PmStatus[]
  pm_due: boolean
  pm_warn: boolean
  down: boolean
  /** PM 后 Qual 状态（B6）：`ready` / `wait_qual`，与 E10 状态无关（D33） */
  qual_state: string
  /** 打开的 Qual 任务 id（待 Qual 时有值） */
  qual_task_id: string | null
}

/** 设备接口客户端。 */
export const eqpApi = {
  board: () =>
    http.get<{ data: BoardRow[] }>('/mes/eqp/board').then((r) => r.data.data),
  changeE10: (
    id: string,
    body: { to_state_id: string; reason_id?: string; comment?: string }
  ) =>
    http
      .post(`/mes/eqp/${id}/e10`, pickBody(body, BODY_KEYS.e10))
      .then((r) => r.data),
  pmComplete: (
    planId: string,
    body: { equipment_id: string; result: 'ok' | 'ng'; comment?: string }
  ) =>
    http
      .post(`/mes/eqp/pm/${planId}/complete`, pickBody(body, BODY_KEYS.pm))
      .then((r) => r.data),
  /** 清除报警（B9）：不自动恢复 E10 状态；已清除时 `cleared=false`（D55）。 */
  alarmClear: (id: string, body: { comment?: string }) =>
    http
      .post<{
        data: Record<string, unknown>
        duplicate: boolean
        cleared: boolean
      }>(`/mes/eqp/alarms/${id}/clear`, pickBody(body, BODY_KEYS.alarmClear))
      .then((r) => r.data),
}

/** 机台上料记录（后端 B3：`/mes/eqp/{eq_id}/mount` 等）。时间为带 Z 的 UTC。 */
export interface MountRow {
  id: string
  equipment_id: string
  port_code: string
  material_lot_id: string
  material_lot_code: string | null
  mounted_at: string
  unmounted_at: string | null
  source: string
  mounted_by: string | null
  comment: string | null
}

/** 人工上料请求：只含可写字段，不传 `source`（人工接口固定为 manual）。 */
export interface MountIn {
  port_code: string
  material_lot_code: string
  external_event_id: string
  comment?: string
}

/** 上料接口客户端。 */
export const mountApi = {
  /** 某时间点机台各上料口装着的料。 */
  at: (eqId: string, at: string) =>
    http
      .get<{
        data: MountRow[]
      }>('/mes/eqp/mount/at', { params: { eq_id: eqId, at } })
      .then((r) => r.data.data),
  /** 人工上料；重复事件号返回 `duplicate=true`，按成功处理。 */
  mount: (eqId: string, body: MountIn) =>
    http
      .post<{
        data: MountRow
        duplicate: boolean
      }>(`/mes/eqp/${eqId}/mount`, pickBody(body, BODY_KEYS.mount))
      .then((r) => r.data),
  /** 卸料（卸下时间默认现在，不带请求体）。 */
  unmount: (mountId: string) =>
    http
      .post<{ data: MountRow }>(`/mes/eqp/mount/${mountId}/unmount`)
      .then((r) => r.data.data),
}
