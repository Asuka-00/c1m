/**
 * 光罩接口（P3，字段按光罩模型 v0.8.2 / eap/p3 50b1db2）。
 * 后端 B4 未就绪前默认走前端 mock（`VITE_RETICLE_MOCK=0` 时改走真实接口）。
 * 请求体一律经 BODY_KEYS 白名单挑选；usage 带 Idempotency-Key（D57）。
 */
import { AxiosError, AxiosHeaders } from 'axios'
import {
  addDecimal,
  compareDecimal,
  decimalText,
  parseDecimal,
} from '@/lib/decimal'
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
  equipment_label: string | null
  mounted_at: string | null
  inspection_required: boolean
  /** v0.8.2 §2 计算字段；B4（335db8a）列表/详情暂未返回，缺省按 inspection_required 显示 */
  inspection_pending?: boolean
  /** 仅动作响应（brief）带：ok / warning / reached */
  life_state?: 'ok' | 'warning' | 'reached'
  last_inspected_at: string | null
  next_inspection_due_at: string | null
}

/** `mes_reticle_status_log`。 */
export interface ReticleStatusLog {
  id: string
  from_status: ReticleStatus | null
  to_status: ReticleStatus
  /** enum reticle_action（下划线：life_reset、clean_start…；含 mount / unmount / inspection / incident / system） */
  action: string
  hold_reason_from: ReticleHoldReason | null
  hold_reason_to: ReticleHoldReason | null
  reason: string | null
  comment: string | null
  trigger: 'manual' | 'system'
  username: string | null
  at: string
}

/** 光罩挂载 / 计数 / 事故的 `source`（D80 G6，迁移 0035 CHECK）。 */
export const RETICLE_SOURCES = ['manual', 'eap', 'simulator', 'system'] as const
export type ReticleSource = (typeof RETICLE_SOURCES)[number]

/** `mes_reticle_usage`。 */
export interface ReticleUsage {
  id: string
  delta: string
  count_after: string
  kind: 'track_out' | 'report' | 'adjust' | 'reset'
  reason_id: string | null
  reason_label?: string | null
  comment: string | null
  source: ReticleSource
  counted: boolean
  estimated: boolean
  lot_id: string | null
  lot_label?: string | null
  username: string | null
  occurred_at: string
}

/**
 * `mes_reticle_mount_log`。D80 G1（be/p3 f9e9dda）：上机一行 `event_type=mount`；下机单独一行
 * `event_type=unmount`，`mount_log_id` 指向上机行（上机行同时回填 unmounted_at 等）。
 */
export interface ReticleMount {
  id: string
  event_type: 'mount' | 'unmount'
  /** 下机行指向的上机行；上机行为 null */
  mount_log_id: string | null
  source: ReticleSource
  external_event_id?: string | null
  equipment_id: string
  equipment_label: string | null
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
  | 'unmount'
  | 'inspection'
  | 'mount'
  | 'incident'

export interface ReticleActionInput {
  delta?: number | string
  reason_id?: string
  note?: string
  reason?: string
  comment?: string
  kind?: string
  result?: string
  defect_count?: number | string
  disposition?: string
  /** mount / incident（MountIn / IncidentIn） */
  equipment_id?: string
  sub_unit_id?: string
  slot_code?: string
  mounted_at?: string
  occurred_at?: string
  lot_id?: string
  description?: string
  unmounted_at?: string
  inspected_at?: string
  /** D82：对话框里的补录时间（站点墙上时间，不提交；提交前换成对应字段） */
  backfill_at?: string
}

/**
 * D80 + 补充一 + 补充二：/mes/reticle 下 14 个手工写接口一律必填 Idempotency-Key
 * （补充二加入 _flow 动态路由的 clean-start / clean-complete / repair-complete / inspect-start）。
 * /mes/eqp 下的物料批上机、下机不在范围内。
 */
export const D80_KEYED = [
  'usage',
  'incident',
  'inspection',
  'mount',
  'unmount',
  'hold',
  'release',
  'restore',
  'life-reset',
  'scrap',
  'clean-start',
  'clean-complete',
  'repair-complete',
  'inspect-start',
] as const satisfies readonly ReticleAction[]
/** 必须带 Idempotency-Key 的光罩动作（= 全部 14 个）。 */
export const IDEMPOTENT: readonly ReticleAction[] = D80_KEYED

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
  unmount: BODY_KEYS.reticleUnmount,
  inspection: BODY_KEYS.reticleInspection,
  mount: BODY_KEYS.reticleMount,
  incident: BODY_KEYS.reticleIncident,
}

/** 按动作挑选请求体（空字符串视为未填）。 */
export function actionBody(action: ReticleAction, input: ReticleActionInput) {
  const clean: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(input))
    if (!(typeof v === 'string' && v.trim() === '')) clean[k] = v
  return pickBody(clean, ACTION_BODY[action])
}

/** 请求体指纹（经 pickBody 白名单、键排序）；用于把 Idempotency-Key 绑定到内容。 */
export function bodySignature(
  action: ReticleAction,
  input: ReticleActionInput
): string {
  const b = actionBody(action, input) as Record<string, unknown>
  return JSON.stringify(
    Object.keys(b)
      .sort()
      .map((k) => [k, b[k]])
  )
}

/** 幂等键绑定：内容不变复用旧 key；内容变了（或首次）生成新 key（后端 H-1）。 */
export function bindKey(
  prev: { sig: string; key: string } | null,
  sig: string,
  gen: () => string
): { sig: string; key: string } {
  return prev && prev.sig === sig ? prev : { sig, key: gen() }
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
  ) => Promise<ReticleActionOut>
  /** 删除（D72：有履历 → 409 referenced；履历表外键 RESTRICT）。 */
  remove: (id: string) => Promise<void>
}

/**
 * 动作响应（B4 335db8a）：多数动作 `{data: 光罩}`；usage / inspection 为
 * `{data: 记录, reticle: 光罩}`；life-reset `{data: 光罩, usage}`；
 * unmount `{data: 上机行, unmount_event: 下机事件行, duplicate?}`（D80 G1）。
 */
export interface ReticleActionOut {
  data: Record<string, unknown>
  reticle?: Reticle
  usage?: ReticleUsage
  /** unmount（D80 G1）：本次下机事件行；`data` 是对应的上机行 */
  unmount_event?: ReticleMount | null
  /** unmount 带 external_event_id（EAP / 模拟器）时才有；手工接口不带 */
  duplicate?: boolean
}

/** 动作响应里的光罩当前行（unmount 不带，返回 null）。 */
export function actionReticle(
  action: ReticleAction,
  out: ReticleActionOut
): Reticle | null {
  if (out.reticle) return out.reticle
  return action === 'unmount' ? null : (out.data as unknown as Reticle)
}

type HistoryItem = Record<string, unknown> & { type: string }

/**
 * `GET /mes/reticle/{id}/history` 的合并列表（type + at）按类型分组。
 * D80 G1：下机事件行 `type=unmount`（at = unmounted_at）不进挂载页签——上机行已回填下机时间、原因和计数，
 * 一次挂载只显示一行。
 */
export function groupHistory(items: HistoryItem[]): ReticleHistory {
  const pick = <T>(type: string) =>
    items.filter((x) => x.type === type) as unknown as T[]
  return {
    status_log: pick<ReticleStatusLog>('status'),
    usage: pick<ReticleUsage>('usage'),
    mounts: pick<ReticleMount>('mount').filter(
      (m) => m.event_type !== 'unmount'
    ),
    inspections: pick<ReticleInspection>('inspection'),
  }
}

/** 真实接口。 */
export const httpReticleApi: Api = {
  list: () =>
    http
      // 通用实体列表 page_size 上限 100（core/pagination.py）
      .get<{ data: Reticle[] }>('/mes/reticle', { params: { page_size: 100 } })
      .then((r) => r.data.data),
  get: (id) => http.get<Reticle>(`/mes/reticle/${id}`).then((r) => r.data),
  history: (id) =>
    http
      .get<{ data: HistoryItem[] }>(`/mes/reticle/${id}/history`, {
        params: { page_size: 200 },
      })
      .then((r) => groupHistory(r.data.data)),
  act: (id, action, input, key) =>
    http
      .post<ReticleActionOut>(
        `/mes/reticle/${id}/${action}`,
        actionBody(action, input),
        IDEMPOTENT.includes(action) && key
          ? { headers: { 'Idempotency-Key': key } }
          : undefined
      )
      .then((r) => r.data),
  remove: (id) => http.delete(`/mes/reticle/${id}`).then(() => undefined),
}

/* ---------------- mock ---------------- */

let mockNow = () => new Date()
/** 测试用：mock 的当前时间。 */
export const setReticleMockNow = (f: () => Date) => {
  mockNow = f
}
const now = () =>
  mockNow()
    .toISOString()
    .replace(/\.\d{3}Z$/, 'Z')

/** D82：补录时间字段（mount / unmount / incident）。 */
export const BACKFILL_FIELD: Partial<
  Record<ReticleAction, 'mounted_at' | 'unmounted_at' | 'occurred_at'>
> = {
  mount: 'mounted_at',
  unmount: 'unmounted_at',
  incident: 'occurred_at',
}
/** mock 校验的事件时间字段：补录三项 + inspection.inspected_at（f9e9dda 同样校验时区 / 超前 / 顺序）。 */
const EVENT_FIELD: Partial<Record<ReticleAction, string>> = {
  ...BACKFILL_FIELD,
  inspection: 'inspected_at',
}
/** 时钟偏差容忍：比当前晚超过 5 分钟拒绝（正好 5:00 放行，D55/D82）。 */
export const CLOCK_SKEW_MS = 5 * 60_000
/** 是否带时区偏移（Z 或 ±hh:mm）。 */
export const hasOffset = (v: string) => /(Z|[+-]\d{2}:\d{2})$/.test(v.trim())
/** 补录时间是否超前当前超过 5 分钟。 */
export const tooFarInFuture = (iso: string, nowMs: number = Date.now()) =>
  Date.parse(iso) - nowMs > CLOCK_SKEW_MS
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
  equipment_label: null,
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
      equipment_label: 'LITHO-01',
      mounted_at: '2026-10-14T01:00:00Z',
    }),
    base({
      id: 'r3',
      code: 'RTC-V1-001',
      layer: 'V1',
      status_code: 'pending_maintenance',
      shot_count: '100000',
      equipment_id: 'e1',
      equipment_label: 'LITHO-01',
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
    event_type: 'mount',
    mount_log_id: null,
    source: 'manual',
    equipment_id: 'e1',
    equipment_label: 'LITHO-01',
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
    lot_id: 'l1',
    lot_label: 'LOT-0001',
    username: 'op1',
    occurred_at: '2026-10-14T03:00:00Z',
  })
  hist.r3.mounts.push({
    id: 'm2',
    event_type: 'mount',
    mount_log_id: null,
    source: 'manual',
    equipment_id: 'e1',
    equipment_label: 'LITHO-01',
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
  /** 下机事件行（D80 G1，后端履历里 type=unmount），只在履历接口合并返回 */
  const unmountEv: Record<string, ReticleMount[]> = {}
  return { r, hist, unmountEv }
}

let store = seed()
const idem = new Map<string, { sig: string; out: ReticleActionOut }>()

/** 测试用：重置 mock 数据。 */
export function resetReticleMock() {
  mockNow = () => new Date()
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
const find = (id: string) => {
  const x = store.r.find((y) => y.id === id)
  if (!x) throw apiError(404, 'not found')
  return x
}
const openMount = (id: string) =>
  store.hist[id].mounts.find((m) => m.unmounted_at == null)

/** 仍有未关闭挂载时 409 still_mounted 的动作（D69 补充）。 */
export const STILL_MOUNTED: ReticleAction[] = [
  'restore',
  'life-reset',
  'repair-complete',
  'inspect-start',
  'clean-start',
]

/** 动作目标状态（null = 非法迁移；unmount 不改状态时返回原状态）。 */
function target(
  x: Reticle,
  a: ReticleAction,
  input: ReticleActionInput
): ReticleStatus | null {
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
    case 'unmount':
      return s === 'in_use' ? 'available' : s
    case 'inspection':
      if (input.result === 'pass')
        return s === 'inspecting' ? 'available' : null
      return s === 'inspecting' || s === 'on_hold' ? 'on_hold' : null
    case 'usage':
      return s
    case 'mount':
      return 'in_use'
    case 'incident':
      return 'on_hold'
  }
}

const num = (v: string | null) => (v == null || v === '' ? null : v)
/** 状态履历 action 枚举（下划线）。 */
const logAction = (a: ReticleAction) => a.replace('-', '_')

/**
 * 请求体 422（N-E2：缺 key 之后、幂等重放和 409 之前，与后端 pydantic 校验同序）。
 */
function bodyCheck(action: ReticleAction, body: ReticleActionInput) {
  // D82：补录时间 —— 无偏移 422 timezone_required；超前 >5 分钟 422 value_error future_time
  const tf = EVENT_FIELD[action] as keyof ReticleActionInput | undefined
  const tv = tf ? body[tf] : undefined
  if (tf && tv != null && tv !== '') {
    if (!hasOffset(String(tv)) || Number.isNaN(Date.parse(String(tv))))
      throw apiError(422, [
        {
          loc: ['body', tf],
          type: 'timezone_required',
          code: 'timezone_required',
          msg: `${tf}: timezone required`,
        },
      ])
    if (tooFarInFuture(String(tv), mockNow().getTime()))
      throw apiError(422, [
        {
          loc: ['body', tf],
          type: 'value_error',
          code: 'value_error',
          msg: `${tf}: more than 5 minutes in the future`,
          ctx: { reason: 'future_time' },
        },
      ])
  }
  if (action === 'usage') {
    const raw = String(body.delta ?? '')
    const d = Number(raw)
    if ((parseDecimal(raw)?.decimals ?? 0) > 6)
      throw apiError(422, [
        {
          loc: ['body', 'delta'],
          type: 'value_error',
          code: 'value_error',
          msg: 'delta: Value error, at most 6 decimal places',
          ctx: { max_places: 6 },
        },
      ])
    if (!Number.isFinite(d) || d === 0)
      throw apiError(422, [
        { loc: ['body', 'delta'], code: 'value_error', msg: 'delta' },
      ])
    if (d < 0 && !body.reason_id)
      throw apiError(422, [
        { loc: ['body', 'reason_id'], code: 'missing', msg: 'reason_id' },
      ])
  }
  if (action === 'mount' && !body.equipment_id)
    throw apiError(422, [
      {
        loc: ['body', 'equipment_id'],
        type: 'missing',
        code: 'missing',
        msg: 'equipment_id: field required',
      },
    ])
  if (
    action === 'incident' &&
    !['collision', 'drop', 'other'].includes(String(body.kind))
  )
    throw apiError(422, [
      {
        loc: ['body', 'kind'],
        type: 'literal_error',
        code: 'literal_error',
        msg: 'kind',
      },
    ])
}

function mockAct(
  id: string,
  action: ReticleAction,
  input: ReticleActionInput,
  key?: string
): ReticleActionOut {
  const body = actionBody(action, input) as ReticleActionInput
  const sig = `${id}|${action}|${bodySignature(action, input)}`
  // D80：缺 key → 422 missing（loc header）
  if (IDEMPOTENT.includes(action) && !key)
    throw apiError(422, [
      {
        loc: ['header', 'Idempotency-Key'],
        type: 'missing',
        code: 'missing',
        msg: 'Idempotency-Key: field required',
      },
    ])
  bodyCheck(action, body)
  if (IDEMPOTENT.includes(action) && key && idem.has(key)) {
    const hit = idem.get(key)!
    // D57/D80：同 key 不同内容 → 422 idempotency_key_reused
    if (hit.sig !== sig)
      throw apiError(422, {
        code: 'idempotency_key_reused',
        message: 'Idempotency-Key reused with a different body',
      })
    // 重放返回原响应（D57）
    return structuredClone(hit.out)
  }
  const x = find(id)
  // D72：scrapped 终态拒绝 usage / 检查录入等全部动作 → 409 invalid_transition
  const conflict = (code: string) =>
    apiError(409, {
      code,
      message: code,
      status_code: x.status_code,
      hold_reason: x.hold_reason,
    })
  // mount（service.mount）：已挂载 409 already_mounted；非 available 409 reticle_unavailable
  if (action === 'mount') {
    if (openMount(id)) throw conflict('already_mounted')
    if (x.status_code !== 'available') throw conflict('reticle_unavailable')
  }
  // D71：先 invalid_transition，再 still_mounted
  const to = target(x, action, body)
  if (to == null) throw conflict('invalid_transition')
  if (STILL_MOUNTED.includes(action) && openMount(id))
    throw conflict('still_mounted')
  if (action === 'unmount' && !openMount(id))
    throw conflict('invalid_transition')
  const h = store.hist[id]
  const from = x.status_code
  const holdFrom = x.hold_reason
  // D82：补录时间；早于最近一次下机 / 事件 409 time_out_of_order；下机早于对应上机 409（相等合法）
  const tf = EVENT_FIELD[action] as keyof ReticleActionInput | undefined
  const given = tf && body[tf] ? String(body[tf]) : null
  const at = given
    ? new Date(Date.parse(given)).toISOString().replace(/\.\d{3}Z$/, 'Z')
    : now()
  if (given) {
    const ms = Date.parse(given)
    // D82：只对 incident，早于最近一次 usage 409（mount / unmount 不算 usage），整笔回滚
    if (
      action === 'incident' &&
      h.usage.some((u) => Date.parse(u.occurred_at) > ms)
    )
      throw conflict('time_out_of_order')
    // 下机 / 登记异常顺带下机：早于当前这次上机 409，整笔不入库、不下机
    if (action === 'unmount' || action === 'incident') {
      const om = openMount(id)
      if (om && ms < Date.parse(om.mounted_at))
        throw conflict('time_out_of_order')
    }
    const last = Math.max(
      ...h.status_log.map((s) => Date.parse(s.at)),
      ...h.mounts
        .filter((m) => m.unmounted_at)
        .map((m) => Date.parse(m.unmounted_at!)),
      -Infinity
    )
    if (ms < last) throw conflict('time_out_of_order')
  }
  const closeMount = (reason: string) => {
    const m = openMount(id)
    if (!m) return null
    m.unmounted_at = at
    m.unmount_reason = reason
    m.shots_at_unmount = x.shot_count
    x.equipment_id = null
    x.equipment_label = null
    x.mounted_at = null
    return m
  }
  let out: ReticleActionOut
  if (action === 'usage') {
    const raw = String(body.delta ?? '')
    const d = Number(raw)
    // 计数按十进制字符串精确累加（D72，不经过浮点）
    const after = addDecimal(x.shot_count, raw) ?? x.shot_count
    if (compareDecimal(after, 0) < 0)
      throw apiError(422, [
        { loc: ['body', 'delta'], code: 'value_error', msg: 'delta' },
      ])
    const before = x.shot_count
    x.shot_count = after
    const row: ReticleUsage = {
      id: `u${Date.now()}`,
      delta: decimalText(raw),
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
    }
    h.usage.unshift(row)
    const max = num(x.max_shots)
    if (
      max != null &&
      compareDecimal(after, max) >= 0 &&
      compareDecimal(before, max) < 0 &&
      (from === 'available' || from === 'in_use')
    )
      x.status_code = 'pending_maintenance'
    out = { data: { ...row }, reticle: { ...x } }
  } else if (action === 'mount') {
    const m: ReticleMount = {
      id: `m${Date.now()}`,
      event_type: 'mount',
      mount_log_id: null,
      source: 'manual',
      equipment_id: body.equipment_id!,
      equipment_label: body.equipment_id!,
      slot_code: body.slot_code?.trim() || null,
      mounted_at: at,
      unmounted_at: null,
      unmount_reason: null,
      shots_at_mount: x.shot_count,
      shots_at_unmount: null,
      username: 'me',
    }
    h.mounts.unshift(m)
    x.status_code = to
    x.equipment_id = m.equipment_id
    x.equipment_label = m.equipment_label
    x.mounted_at = m.mounted_at
    x.mount_count += 1
    out = { data: { ...m } }
  } else if (action === 'incident') {
    // 非 scrapped 一律 on_hold(incident) + 待检（service.incident / system_hold）
    if (from !== 'on_hold')
      x.status_before_hold = from === 'in_use' ? 'available' : from
    closeMount('incident')
    x.hold_reason = 'incident'
    x.status_code = to
    x.inspection_required = true
    x.inspection_pending = true
    out = {
      data: {
        id: `inc${Date.now()}`,
        kind: body.kind,
        occurred_at: at,
        equipment_id: body.equipment_id ?? null,
        lot_id: body.lot_id ?? null,
        description: body.description ?? null,
        source: 'manual',
      },
      reticle: { ...x },
    }
  } else if (action === 'unmount') {
    const m = closeMount('manual')!
    x.status_code = to
    // D80 G1：data 为上机行，unmount_event 为下机事件行（手工接口不带 duplicate）
    const ev: ReticleMount = {
      ...m,
      id: `${m.id}-u${Date.now()}`,
      event_type: 'unmount',
      mount_log_id: m.id,
    }
    ;(store.unmountEv[id] ??= []).push({ ...ev })
    out = { data: { ...m }, unmount_event: ev }
  } else {
    if (action === 'restore') {
      const max = num(x.max_shots)
      if (max != null && compareDecimal(x.shot_count, max) >= 0)
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
    } else if (action === 'inspection') {
      h.inspections.unshift({
        id: `i${Date.now()}`,
        kind: (body.kind ?? 'other') as ReticleInspection['kind'],
        result: body.result as ReticleInspection['result'],
        defect_count:
          body.defect_count == null ? null : Number(body.defect_count),
        disposition: (body.disposition ??
          'none') as ReticleInspection['disposition'],
        shots_at_inspection: x.shot_count,
        comment: body.comment ?? null,
        username: 'me',
        inspected_at: at,
      })
      if (body.result === 'pass') {
        x.inspection_required = false
        x.inspection_pending = false
      } else {
        if (from !== 'on_hold') x.status_before_hold = from
        x.hold_reason = 'inspection_failed'
      }
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
    out =
      action === 'inspection'
        ? { data: { ...h.inspections[0] }, reticle: { ...x } }
        : action === 'life-reset'
          ? { data: { ...x }, usage: { ...h.usage[0] } }
          : { data: { ...x } }
  }
  if (x.status_code !== from || x.hold_reason !== holdFrom)
    h.status_log.unshift({
      id: `s${Date.now()}`,
      from_status: from,
      to_status: x.status_code,
      action: action === 'usage' ? 'system' : logAction(action),
      hold_reason_from: holdFrom,
      hold_reason_to: x.hold_reason,
      reason: ['hold', 'restore', 'scrap'].includes(action)
        ? (body.reason ?? null)
        : null,
      comment: body.comment ?? null,
      trigger: action === 'usage' ? 'system' : 'manual',
      username: 'me',
      at,
    })
  if (IDEMPOTENT.includes(action) && key)
    idem.set(key, { sig, out: structuredClone(out) })
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

/** 是否有任何履历（状态 / 计数 / 挂载 / 检查）。 */
export function hasHistory(h: ReticleHistory) {
  return (
    h.status_log.length +
      h.usage.length +
      h.mounts.length +
      h.inspections.length >
    0
  )
}

/** 有记录的履历表名（409 referenced 的 tables）。 */
export function referencedTables(h: ReticleHistory): string[] {
  // 顺序与后端 reticle/validators.HISTORY 一致（incident 在 mock 里没有单独履历）
  const t: string[] = []
  if (h.mounts.length) t.push('mes_reticle_mount_log')
  if (h.usage.length) t.push('mes_reticle_usage')
  if (h.inspections.length) t.push('mes_reticle_inspection')
  if (h.status_log.length) t.push('mes_reticle_status_log')
  return t
}

function mockRemove(id: string) {
  find(id)
  // D72：有履历的光罩不能删 → 409 {code:'referenced', message, tables}（履历表外键 RESTRICT）
  const tables = referencedTables(store.hist[id])
  if (tables.length)
    throw apiError(409, {
      code: 'referenced',
      message: 'reticle has history; scrap it instead',
      tables,
    })
  store.r = store.r.filter((y) => y.id !== id)
  delete store.hist[id]
}

/** 前端 mock 实现（同形数据与错误码）。 */
export const mockReticleApi: Api = {
  list: () => later(() => store.r),
  get: (id) => later(() => find(id)),
  history: (id) => {
    // QA P3-1：与真实接口同形——合并列表（type + 行）再经 groupHistory 分组，下机行在这里被过滤
    return later(() => {
      find(id)
      const h = store.hist[id]
      const tag = (type: string, rows: object[]) =>
        rows.map((x) => ({ ...x, type }))
      return groupHistory([
        ...tag('status', h.status_log),
        ...tag('usage', h.usage),
        ...tag('mount', h.mounts),
        ...tag('unmount', store.unmountEv[id] ?? []),
        ...tag('inspection', h.inspections),
      ])
    })
  },
  act: (id, action, input, key) => later(() => mockAct(id, action, input, key)),
  remove: (id) => later(() => mockRemove(id)),
}

/** 是否使用 mock（后端 B4 就绪后设 VITE_RETICLE_MOCK=0）。 */
export const RETICLE_MOCK = import.meta.env.VITE_RETICLE_MOCK !== '0'

export const reticleApi: Api = RETICLE_MOCK ? mockReticleApi : httpReticleApi
