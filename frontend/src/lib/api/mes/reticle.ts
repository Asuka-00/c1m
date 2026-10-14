/**
 * 光罩接口（P3，字段按光罩模型 v0.8.2 / eap/p3 50b1db2）。
 * 后端 B4 未就绪前默认走前端 mock（`VITE_RETICLE_MOCK=0` 时改走真实接口）。
 * 请求体一律经 BODY_KEYS 白名单挑选；usage 带 Idempotency-Key（D57）。
 */
import { AxiosError, AxiosHeaders } from 'axios'
import { http } from '../client'
import { BODY_KEYS, pickBody } from '../request-body'

/** 光罩专用状态枚举 `reticle_status`（终态 scrapped）。 */
export const RETICLE_STATUSES = [
  'available',
  'in_use',
  'dirty',
  'inspecting',
  'on_hold',
  'pending_maintenance',
  'scrapped',
] as const
export type ReticleStatus = (typeof RETICLE_STATUSES)[number]
export type ReticleHoldReason = 'incident' | 'inspection_failed' | 'manual'

/** `mes_reticle`（status_code / hold_reason / status_before_hold 只读）。 */
export interface Reticle {
  id: string
  code: string
  name: string
  revision: string | null
  grade: string | null
  layer: string | null
  status_code: ReticleStatus
  hold_reason: ReticleHoldReason | null
  status_before_hold: ReticleStatus | null
  shot_count: string
  max_shots: string | null
  warn_ratio: string | null
  mount_count: number
  life_reset_count: number
  count_basis: 'track_out' | 'eap'
  storage_location: string | null
  equipment_id: string | null
  equipment_code: string | null
  mounted_at: string | null
  inspection_required: boolean
  inspection_pending: boolean
  last_inspected_at: string | null
  next_inspection_due_at: string | null
}

/** `mes_reticle_status_log`。 */
export interface ReticleStatusLog {
  id: string
  from_status: ReticleStatus | null
  to_status: ReticleStatus
  action: string
  hold_reason_from: ReticleHoldReason | null
  hold_reason_to: ReticleHoldReason | null
  reason: string | null
  comment: string | null
  trigger: 'manual' | 'system'
  username: string | null
  at: string
}

/** `mes_reticle_usage`。 */
export interface ReticleUsage {
  id: string
  delta: string
  count_after: string
  kind: 'track_out' | 'report' | 'adjust' | 'reset'
  reason_id: string | null
  comment: string | null
  source: string
  counted: boolean
  estimated: boolean
  lot_id: string | null
  username: string | null
  occurred_at: string
}

/** `mes_reticle_mount_log`。 */
export interface ReticleMount {
  id: string
  equipment_id: string
  equipment_code: string | null
  slot_code: string | null
  mounted_at: string
  unmounted_at: string | null
  unmount_reason: string | null
  shots_at_mount: string
  shots_at_unmount: string | null
  username: string | null
}

/** `mes_reticle_inspection`。 */
export interface ReticleInspection {
  id: string
  kind: 'particle' | 'haze' | 'cd' | 'other'
  result: 'pass' | 'fail'
  defect_count: number | null
  disposition: 'none' | 'clean' | 'hold' | 'repair' | 'scrap'
  shots_at_inspection: string
  comment: string | null
  username: string | null
  inspected_at: string
}

export interface ReticleHistory {
  status_log: ReticleStatusLog[]
  usage: ReticleUsage[]
  mounts: ReticleMount[]
  inspections: ReticleInspection[]
}

/** 状态动作（POST /mes/reticle/{id}/<action>）。 */
export type ReticleAction =
  | 'usage'
  | 'hold'
  | 'release'
  | 'restore'
  | 'clean-start'
  | 'clean-complete'
  | 'repair-complete'
  | 'inspect-start'
  | 'scrap'
  | 'life-reset'

export interface ReticleActionInput {
  delta?: number | string
  reason_id?: string
  note?: string
  reason?: string
  comment?: string
}

/** 各动作请求体白名单。 */
export const ACTION_BODY: Record<ReticleAction, readonly string[]> = {
  usage: BODY_KEYS.reticleUsage,
  hold: BODY_KEYS.reticleReason,
  restore: BODY_KEYS.reticleReason,
  scrap: BODY_KEYS.reticleReason,
  'life-reset': BODY_KEYS.reticleReason,
  release: BODY_KEYS.reticleComment,
  'clean-start': BODY_KEYS.reticleComment,
  'clean-complete': BODY_KEYS.reticleComment,
  'repair-complete': BODY_KEYS.reticleComment,
  'inspect-start': BODY_KEYS.reticleComment,
}

/** 按动作挑选请求体（空字符串视为未填）。 */
export function actionBody(action: ReticleAction, input: ReticleActionInput) {
  const clean: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(input))
    if (!(typeof v === 'string' && v.trim() === '')) clean[k] = v
  return pickBody(clean, ACTION_BODY[action])
}

interface Api {
  list: () => Promise<Reticle[]>
  get: (id: string) => Promise<Reticle>
  history: (id: string) => Promise<ReticleHistory>
  act: (
    id: string,
    action: ReticleAction,
    input: ReticleActionInput,
    idempotencyKey?: string
  ) => Promise<Reticle>
}

/** 真实接口。 */
export const httpReticleApi: Api = {
  list: () =>
    http
      .get<{ data: Reticle[] }>('/mes/reticle', { params: { page_size: 200 } })
      .then((r) => r.data.data),
  get: (id) => http.get<Reticle>(`/mes/reticle/${id}`).then((r) => r.data),
  history: (id) =>
    http.get<ReticleHistory>(`/mes/reticle/${id}/history`).then((r) => r.data),
  act: (id, action, input, key) =>
    http
      .post<Reticle>(
        `/mes/reticle/${id}/${action}`,
        actionBody(action, input),
        action === 'usage' && key
          ? { headers: { 'Idempotency-Key': key } }
          : undefined
      )
      .then((r) => r.data),
}

/* ---------------- mock ---------------- */

const now = () => new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')
const base = (o: Partial<Reticle> & Pick<Reticle, 'id' | 'code'>): Reticle => ({
  name: o.code,
  revision: 'A',
  grade: 'binary',
  layer: 'M1',
  status_code: 'available',
  hold_reason: null,
  status_before_hold: null,
  shot_count: '0',
  max_shots: '100000',
  warn_ratio: null,
  mount_count: 0,
  life_reset_count: 0,
  count_basis: 'track_out',
  storage_location: 'STK-01-A01',
  equipment_id: null,
  equipment_code: null,
  mounted_at: null,
  inspection_required: false,
  inspection_pending: false,
  last_inspected_at: '2026-10-01T02:00:00Z',
  next_inspection_due_at: '2026-11-01T02:00:00Z',
  ...o,
})

function seed() {
  const r: Reticle[] = [
    base({ id: 'r1', code: 'RTC-M1-001', shot_count: '1200' }),
    base({
      id: 'r2',
      code: 'RTC-M1-002',
      status_code: 'in_use',
      shot_count: '45000',
      mount_count: 3,
      equipment_id: 'e1',
      equipment_code: 'LITHO-01',
      mounted_at: '2026-10-14T01:00:00Z',
    }),
    base({
      id: 'r3',
      code: 'RTC-V1-001',
      layer: 'V1',
      status_code: 'pending_maintenance',
      shot_count: '100000',
      equipment_id: 'e1',
      equipment_code: 'LITHO-01',
      mounted_at: '2026-10-13T01:00:00Z',
    }),
    base({
      id: 'r4',
      code: 'RTC-V1-002',
      layer: 'V1',
      status_code: 'on_hold',
      hold_reason: 'incident',
      status_before_hold: 'available',
      inspection_required: true,
      inspection_pending: true,
    }),
    base({ id: 'r5', code: 'RTC-M2-001', status_code: 'dirty' }),
    base({
      id: 'r6',
      code: 'RTC-M2-002',
      status_code: 'inspecting',
      inspection_required: true,
      inspection_pending: true,
    }),
    base({ id: 'r7', code: 'RTC-OLD-001', status_code: 'scrapped' }),
  ]
  const hist: Record<string, ReticleHistory> = {}
  for (const x of r)
    hist[x.id] = { status_log: [], usage: [], mounts: [], inspections: [] }
  hist.r2.mounts.push({
    id: 'm1',
    equipment_id: 'e1',
    equipment_code: 'LITHO-01',
    slot_code: 'S1',
    mounted_at: '2026-10-14T01:00:00Z',
    unmounted_at: null,
    unmount_reason: null,
    shots_at_mount: '40000',
    shots_at_unmount: null,
    username: 'op1',
  })
  hist.r2.usage.push({
    id: 'u1',
    delta: '5000',
    count_after: '45000',
    kind: 'track_out',
    reason_id: null,
    comment: null,
    source: 'manual',
    counted: true,
    estimated: false,
    lot_id: 'LOT-0001',
    username: 'op1',
    occurred_at: '2026-10-14T03:00:00Z',
  })
  hist.r3.mounts.push({
    id: 'm2',
    equipment_id: 'e1',
    equipment_code: 'LITHO-01',
    slot_code: 'S2',
    mounted_at: '2026-10-13T01:00:00Z',
    unmounted_at: null,
    unmount_reason: null,
    shots_at_mount: '90000',
    shots_at_unmount: null,
    username: 'op1',
  })
  hist.r3.status_log.push({
    id: 's1',
    from_status: 'in_use',
    to_status: 'pending_maintenance',
    action: 'system',
    hold_reason_from: null,
    hold_reason_to: null,
    reason: null,
    comment: null,
    trigger: 'system',
    username: null,
    at: '2026-10-14T04:00:00Z',
  })
  hist.r4.status_log.push({
    id: 's2',
    from_status: 'available',
    to_status: 'on_hold',
    action: 'incident',
    hold_reason_from: null,
    hold_reason_to: 'incident',
    reason: null,
    comment: null,
    trigger: 'system',
    username: 'op2',
    at: '2026-10-14T05:00:00Z',
  })
  hist.r6.inspections.push({
    id: 'i1',
    kind: 'particle',
    result: 'fail',
    defect_count: 3,
    disposition: 'clean',
    shots_at_inspection: '0',
    comment: null,
    username: 'qa1',
    inspected_at: '2026-10-12T05:00:00Z',
  })
  return { r, hist }
}

let store = seed()
const idem = new Map<string, Reticle>()

/** 测试用：重置 mock 数据。 */
export function resetReticleMock() {
  store = seed()
  idem.clear()
}

/** 构造与后端同形的错误（409 对象 detail / 422 列表 detail）。 */
export function apiError(status: number, detail: unknown) {
  return new AxiosError('mock', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: { detail },
  })
}
const conflict = (code: string) => apiError(409, { code, message: code })

const find = (id: string) => {
  const x = store.r.find((y) => y.id === id)
  if (!x) throw apiError(404, 'not found')
  return x
}
const openMount = (id: string) =>
  store.hist[id].mounts.find((m) => m.unmounted_at == null)

const STILL_MOUNTED: ReticleAction[] = [
  'restore',
  'life-reset',
  'repair-complete',
  'inspect-start',
  'clean-start',
]

/** 动作目标状态（null = 非法迁移）。 */
function target(x: Reticle, a: ReticleAction): ReticleStatus | null {
  const s = x.status_code
  if (s === 'scrapped') return null
  switch (a) {
    case 'hold':
      return s === 'on_hold' ? null : 'on_hold'
    case 'release':
      if (s !== 'on_hold') return null
      return x.hold_reason === 'incident'
        ? 'inspecting'
        : x.hold_reason === 'inspection_failed'
          ? 'pending_maintenance'
          : (x.status_before_hold ?? 'available')
    case 'restore':
    case 'life-reset':
      return s === 'pending_maintenance' ? 'available' : null
    case 'clean-start':
      return s === 'available' ? 'dirty' : null
    case 'clean-complete':
      return s === 'dirty' ? 'inspecting' : null
    case 'repair-complete':
      return s === 'pending_maintenance' ? 'inspecting' : null
    case 'inspect-start':
      return s === 'available' ? 'inspecting' : null
    case 'scrap':
      return 'scrapped'
    case 'usage':
      return s
  }
}

const num = (v: string | null) => (v == null ? null : Number(v))

function mockAct(
  id: string,
  action: ReticleAction,
  input: ReticleActionInput,
  key?: string
): Reticle {
  const body = actionBody(action, input) as ReticleActionInput
  if (action === 'usage' && key && idem.has(key)) return { ...idem.get(key)! }
  const x = find(id)
  const to = target(x, action)
  if (to == null) throw conflict('invalid_transition')
  if (STILL_MOUNTED.includes(action) && openMount(id))
    throw conflict('still_mounted')
  const h = store.hist[id]
  const from = x.status_code
  const at = now()
  const closeMount = (reason: string) => {
    const m = openMount(id)
    if (!m) return null
    m.unmounted_at = at
    m.unmount_reason = reason
    m.shots_at_unmount = x.shot_count
    x.equipment_id = null
    x.equipment_code = null
    x.mounted_at = null
    return m
  }
  if (action === 'usage') {
    const d = Number(body.delta)
    if (!Number.isFinite(d) || d === 0)
      throw apiError(422, [
        { loc: ['body', 'delta'], code: 'value_error', msg: 'delta' },
      ])
    if (d < 0 && !body.reason_id)
      throw apiError(422, [
        { loc: ['body', 'reason_id'], code: 'missing', msg: 'reason_id' },
      ])
    const after = Number(x.shot_count) + d
    if (after < 0)
      throw apiError(422, [
        { loc: ['body', 'delta'], code: 'value_error', msg: 'delta' },
      ])
    x.shot_count = String(after)
    h.usage.unshift({
      id: `u${Date.now()}`,
      delta: String(d),
      count_after: x.shot_count,
      kind: d > 0 ? 'report' : 'adjust',
      reason_id: body.reason_id ?? null,
      comment: body.note ?? null,
      source: 'manual',
      counted: true,
      estimated: false,
      lot_id: null,
      username: 'me',
      occurred_at: at,
    })
    const max = num(x.max_shots)
    if (
      max != null &&
      after >= max &&
      (from === 'available' || from === 'in_use')
    )
      x.status_code = 'pending_maintenance'
  } else {
    if (action === 'restore') {
      const max = num(x.max_shots)
      if (max != null && Number(x.shot_count) >= max)
        throw conflict('life_limit_reached')
    }
    if (action === 'life-reset') {
      x.shot_count = '0'
      x.life_reset_count += 1
      h.usage.unshift({
        id: `u${Date.now()}`,
        delta: '0',
        count_after: '0',
        kind: 'reset',
        reason_id: null,
        comment: body.reason ?? null,
        source: 'manual',
        counted: true,
        estimated: false,
        lot_id: null,
        username: 'me',
        occurred_at: at,
      })
    }
    if (action === 'hold') {
      x.status_before_hold = from === 'in_use' ? 'available' : from
      x.hold_reason = 'manual'
      closeMount('hold')
    } else if (action === 'scrap') {
      closeMount('scrap')
      x.hold_reason = null
      x.status_before_hold = null
    } else if (action === 'release') {
      x.hold_reason = null
      x.status_before_hold = null
    }
    if (
      ['restore', 'life-reset', 'clean-complete', 'repair-complete'].includes(
        action
      )
    ) {
      x.inspection_required = true
      x.inspection_pending = true
    }
    x.status_code = to
  }
  if (x.status_code !== from || action !== 'usage')
    h.status_log.unshift({
      id: `s${Date.now()}`,
      from_status: from,
      to_status: x.status_code,
      action: action === 'usage' ? 'system' : action,
      hold_reason_from: null,
      hold_reason_to: x.hold_reason,
      reason: ['hold', 'restore', 'scrap'].includes(action)
        ? (body.reason ?? null)
        : null,
      comment: body.comment ?? null,
      trigger: action === 'usage' ? 'system' : 'manual',
      username: 'me',
      at,
    })
  const out = { ...x }
  if (action === 'usage' && key) idem.set(key, out)
  return out
}

const later = <T>(f: () => T) =>
  new Promise<T>((res, rej) => {
    try {
      res(structuredClone(f()))
    } catch (e) {
      rej(e)
    }
  })

/** 前端 mock 实现（同形数据与错误码）。 */
export const mockReticleApi: Api = {
  list: () => later(() => store.r),
  get: (id) => later(() => find(id)),
  history: (id) => {
    return later(() => {
      find(id)
      return store.hist[id]
    })
  },
  act: (id, action, input, key) => later(() => mockAct(id, action, input, key)),
}

/** 是否使用 mock（后端 B4 就绪后设 VITE_RETICLE_MOCK=0）。 */
export const RETICLE_MOCK = import.meta.env.VITE_RETICLE_MOCK !== '0'

export const reticleApi: Api = RETICLE_MOCK ? mockReticleApi : httpReticleApi
