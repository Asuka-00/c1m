/**
 * P3-F2 / B6 人员资质履历（D74 及补充 Q6-1/Q6-2，见 docs/p3-operator-qual.md）。
 *
 * - 履历表 `mes_operator_qual_log`：action（granted/renewed/changed/deactivated/reactivated/expired）、
 *   before/after（变更字段快照）、reason_id、comment（≤300）、approved_by（≤64）、username、at（UTC Z）。
 * - 履历接口 `GET /mes/exec/operator-qual/{qual_id}/history`（mes.exec:read，403 > 404），
 *   返回 `{rows}`，按 at 倒序，`limit` 默认 50、最大 200，`offset`。
 * - 写入（授予 / 延期 / 变更 / 停用 / 恢复）每次一条履历 + 一条 `operator_qual.*` 事件；
 *   写接口必须带 Idempotency-Key（B6 验收要点），顺序按 D81：
 *   403 → 缺 key 422 → 请求体 422（停用 / 延期缺 reason_id、comment，延期缺 approved_by → missing）
 *   → 幂等重放 / reused → 404 → 需查记录的 422（self_approval）→ 409。
 * - 过期不自动停用（Q6-1）：每日扫描写 action=expired 履历并发 `operator_qual.expired`，is_active 不变。
 * - 本实体没有带 scale 的数值字段（D76 不涉及）；expires_on / certified_on 为站点日期 YYYY-MM-DD（D75）。
 */
import { siteToday } from '@/lib/site-tz'
import {
  QUAL_WARN_DAYS,
  warnDaysOf,
} from '@/features/mes/execution/operator-qual'
import { http } from '../client'
import { apiError } from './mock-utils'

export const QUAL_LOG_ACTIONS = [
  'granted',
  'renewed',
  'changed',
  'deactivated',
  'reactivated',
  'expired',
] as const
export type QualLogAction = (typeof QUAL_LOG_ACTIONS)[number]

/** 履历行（mes_operator_qual_log）。 */
export interface QualLogRow {
  id: string
  qual_id: string
  action: QualLogAction
  /** 变更前的字段快照（granted 为 null） */
  before: Record<string, unknown> | null
  /** 变更后的字段快照（expired 为 {expires_on}） */
  after: Record<string, unknown> | null
  reason_id: string | null
  comment: string | null
  approved_by: string | null
  /** 操作人（定时扫描为 system） */
  username: string
  /** UTC，Z 结尾 */
  at: string
}

export interface QualHistoryPage {
  rows: QualLogRow[]
}

/** 资质记录（mes_operator_qual 中履历关心的字段）。 */
export interface OperatorQual {
  id: string
  /** 被授予资质的操作员 */
  username: string
  operation_id: string
  equipment_type_id: string | null
  certified_on: string | null
  expires_on: string | null
  is_active: boolean
}

export type QualInput = Omit<OperatorQual, 'id'>

/** 写请求体顶层放行的原因字段（Q6-2）。 */
export interface QualReason {
  reason_id?: string | null
  comment?: string | null
  approved_by?: string | null
}

export const QUAL_COMMENT_MAX = 300
export const QUAL_APPROVED_BY_MAX = 64
export const QUAL_HISTORY_LIMIT_DEFAULT = 50
export const QUAL_HISTORY_LIMIT_MAX = 200
/** 进站检查项（D74：沿用现有 operator_qualified；见回报待确认项）。 */
export const QUAL_CHECK_TYPE = 'operator_qualified'

export interface QualHistoryApi {
  history: (
    qualId: string,
    q?: { limit?: number; offset?: number }
  ) => Promise<QualHistoryPage>
}

export const httpQualHistoryApi: QualHistoryApi = {
  history: (qualId, q) =>
    http
      .get<QualHistoryPage>(`/mes/exec/operator-qual/${qualId}/history`, {
        params: q,
      })
      .then((r) => r.data),
}

// ───────────────────────── mock ─────────────────────────

export interface QualEvent {
  type: string
  qual_id: string
  username: string
  operation_id: string
  equipment_type_id: string | null
  occurred_at: string
  actor: string
  [k: string]: unknown
}

interface Store {
  q: OperatorQual[]
  log: QualLogRow[]
  events: QualEvent[]
  n: number
}

const seedQuals = (): OperatorQual[] => [
  {
    id: 'q1',
    username: 'op1',
    operation_id: 'DA',
    equipment_type_id: null,
    certified_on: '2026-01-05',
    expires_on: '2026-10-20',
    is_active: true,
  },
  {
    id: 'q2',
    username: 'op2',
    operation_id: 'WB',
    equipment_type_id: 'WB-ASM',
    certified_on: '2025-10-01',
    expires_on: '2026-10-10',
    is_active: true,
  },
]

let store: Store = { q: [], log: [], events: [], n: 0 }
let mockUser = 'admin'
let mockPerms: string[] | null = null
let mockNow: () => Date = () => new Date()
let mockWarnDays: unknown = QUAL_WARN_DAYS
const idem = new Map<string, { sig: string; out: unknown }>()

const READ = 'mes.exec:read'
const WRITE = 'mes.exec:write'
const isoNow = () =>
  mockNow()
    .toISOString()
    .replace(/\.\d{3}Z$/, 'Z')

/** 测试用：重置 mock（两条资质，各带一条 granted 履历）。 */
export function resetQualHistoryMock() {
  store = { q: seedQuals(), log: [], events: [], n: 0 }
  idem.clear()
  mockUser = 'admin'
  mockPerms = null
  mockNow = () => new Date()
  mockWarnDays = QUAL_WARN_DAYS
  for (const x of store.q)
    store.log.push({
      id: `l${++store.n}`,
      qual_id: x.id,
      action: 'granted',
      before: null,
      after: { ...snap(x) },
      reason_id: null,
      comment: null,
      approved_by: null,
      username: 'admin',
      at: `${x.certified_on}T01:00:00Z`,
    })
}
export const setQualMockUser = (u: string) => {
  mockUser = u
}
export const setQualMockPerms = (p: string[] | null) => {
  mockPerms = p
}
export const setQualMockNow = (f: () => Date) => {
  mockNow = f
}
/** 预警天数的唯一来源（operator_qual 元数据 warn_days，缺失 / 非法按 30）。 */
export const setQualMockWarnDays = (v: unknown) => {
  mockWarnDays = v
}
export const qualMockWarnDays = () => warnDaysOf(mockWarnDays)
/** 测试用：已发出的事件。 */
export const qualMockEvents = () => structuredClone(store.events)

const SNAP_KEYS = [
  'certified_on',
  'expires_on',
  'is_active',
  'operation_id',
  'equipment_type_id',
] as const
function snap(x: Partial<OperatorQual>) {
  const o: Record<string, unknown> = {}
  for (const k of SNAP_KEYS) if (k in x) o[k] = x[k]
  return o
}

const later = <T>(f: () => T): Promise<T> =>
  new Promise((res, rej) =>
    setTimeout(() => {
      try {
        res(structuredClone(f()))
      } catch (e) {
        rej(e)
      }
    }, 0)
  )
const need = (perm: string) => {
  if (mockPerms && !mockPerms.includes(perm))
    throw apiError(403, 'Not enough permissions')
}
const missing = (loc: string, where: 'body' | 'header' = 'body') =>
  apiError(422, [
    {
      loc: [where, loc],
      type: 'missing',
      code: 'missing',
      msg: `${loc}: field required`,
    },
  ])
const valueErr = (loc: string, msg: string, ctx?: Record<string, unknown>) =>
  apiError(422, [
    { loc: ['body', loc], type: 'value_error', code: 'value_error', msg, ctx },
  ])
const findQ = (id: string) => {
  const x = store.q.find((y) => y.id === id)
  if (!x) throw apiError(404, 'not found')
  return x
}
const blank = (v: unknown) => v == null || String(v).trim() === ''

/** 写入意图（仅由请求体判断，供请求体 422 使用，先于 404）。 */
export type QualIntent = 'deactivate' | 'renew' | 'other'
export function qualIntent(body: Partial<QualInput> & QualReason): QualIntent {
  if (body.is_active === false) return 'deactivate'
  if (body.expires_on != null && body.expires_on !== '') return 'renew'
  return 'other'
}

/** 请求体 422（Q6-2）：停用 / 延期必填 reason_id、comment，延期另需 approved_by；comment ≤300。 */
export function qualBodyCheck(body: Partial<QualInput> & QualReason) {
  const intent = qualIntent(body)
  if (intent !== 'other') {
    if (blank(body.reason_id)) throw missing('reason_id')
    if (blank(body.comment)) throw missing('comment')
    if (intent === 'renew' && blank(body.approved_by))
      throw missing('approved_by')
  }
  if (
    typeof body.comment === 'string' &&
    [...body.comment].length > QUAL_COMMENT_MAX
  )
    throw valueErr('comment', 'comment: at most 300 characters', {
      reason: 'max_length',
      max_length: QUAL_COMMENT_MAX,
    })
  if (
    typeof body.approved_by === 'string' &&
    [...body.approved_by].length > QUAL_APPROVED_BY_MAX
  )
    throw valueErr('approved_by', 'approved_by: at most 64 characters', {
      reason: 'max_length',
      max_length: QUAL_APPROVED_BY_MAX,
    })
}

function withKey<T>(key: string, sig: string, f: () => T, pre: () => void): T {
  if (!key) throw missing('Idempotency-Key', 'header')
  pre()
  const hit = idem.get(key)
  if (hit) {
    if (hit.sig !== sig)
      throw apiError(422, {
        code: 'idempotency_key_reused',
        message: 'Idempotency-Key reused with a different body',
      })
    return structuredClone(hit.out) as T
  }
  const out = f()
  idem.set(key, { sig, out: structuredClone(out) })
  return out
}

const sigOf = (op: string, body: object) =>
  `${op}:${JSON.stringify(body, Object.keys(body).sort())}`

function record(
  x: OperatorQual,
  action: QualLogAction,
  before: Record<string, unknown> | null,
  after: Record<string, unknown> | null,
  r: QualReason,
  actor = mockUser,
  extra: Record<string, unknown> = {}
) {
  const at = isoNow()
  store.log.push({
    id: `l${++store.n}`,
    qual_id: x.id,
    action,
    before,
    after,
    reason_id: r.reason_id ?? null,
    comment: r.comment ?? null,
    approved_by: r.approved_by ?? null,
    username: actor,
    at,
  })
  // 事件（domain-events.md）：reactivated 只写履历，不在 D74 事件清单里
  if (action === 'reactivated') return
  store.events.push({
    type: `operator_qual.${action}`,
    qual_id: x.id,
    username: x.username,
    operation_id: x.operation_id,
    equipment_type_id: x.equipment_type_id,
    occurred_at: at,
    actor,
    ...extra,
  })
}

function mockGrant(input: QualInput & QualReason): OperatorQual {
  const x: OperatorQual = {
    id: `q${store.q.length + 1}-${++store.n}`,
    username: input.username,
    operation_id: input.operation_id,
    equipment_type_id: input.equipment_type_id ?? null,
    certified_on: input.certified_on ?? null,
    expires_on: input.expires_on ?? null,
    is_active: input.is_active ?? true,
  }
  store.q.push(x)
  record(x, 'granted', null, snap(x), input, mockUser, {
    certified_on: x.certified_on,
    expires_on: x.expires_on,
    reason_id: input.reason_id ?? null,
    comment: input.comment ?? null,
  })
  return x
}

function mockUpdate(
  id: string,
  body: Partial<QualInput> & QualReason
): OperatorQual {
  const x = findQ(id)
  const intent = qualIntent(body)
  // Q6-2 补充：延期的 approved_by 不能是被授予人本人（需查到记录才能判断，404 之后、409 之前）
  if (intent === 'renew' && body.approved_by === x.username)
    throw valueErr('approved_by', 'approver cannot be the operator', {
      reason: 'self_approval',
    })
  if (intent === 'deactivate' && !x.is_active)
    throw apiError(409, {
      code: 'invalid_transition',
      message: 'qualification is already inactive',
    })
  const patch: Partial<OperatorQual> = {}
  for (const k of SNAP_KEYS)
    if (k in body && body[k] !== undefined)
      (patch as Record<string, unknown>)[k] = body[k]
  const changed = Object.keys(patch).filter(
    (k) => patch[k as keyof OperatorQual] !== x[k as keyof OperatorQual]
  ) as (typeof SNAP_KEYS)[number][]
  if (!changed.length) return x
  const before = snap(
    Object.fromEntries(changed.map((k) => [k, x[k]])) as Partial<OperatorQual>
  )
  const after = snap(patch)
  const prev = { ...x }
  Object.assign(x, patch)
  const r: QualReason = body
  if (changed.includes('is_active') && prev.is_active && !x.is_active)
    record(x, 'deactivated', before, after, r, mockUser, {
      reason_id: r.reason_id,
      reason_code: r.reason_id,
      comment: r.comment,
    })
  else if (changed.includes('is_active') && !prev.is_active && x.is_active)
    record(x, 'reactivated', before, after, r)
  else if (
    changed.includes('expires_on') &&
    (prev.expires_on == null ||
      (x.expires_on != null && x.expires_on > prev.expires_on))
  )
    record(x, 'renewed', before, after, r, mockUser, {
      expires_on_before: prev.expires_on,
      expires_on: x.expires_on,
      reason_id: r.reason_id,
      reason_code: r.reason_id,
      comment: r.comment,
      approved_by: r.approved_by,
    })
  else
    record(x, 'changed', before, after, r, mockUser, {
      changes: Object.fromEntries(changed.map((k) => [k, [prev[k], x[k]]])),
      reason_id: r.reason_id ?? null,
      comment: r.comment ?? null,
    })
  return x
}

function mockRemove(id: string) {
  const x = findQ(id)
  if (store.log.some((l) => l.qual_id === x.id))
    throw apiError(409, {
      code: 'referenced',
      message: 'qualification has history; deactivate it instead',
      tables: ['mes_operator_qual_log'],
    })
  store.q = store.q.filter((y) => y.id !== id)
}

function mockHistory(
  qualId: string,
  q: { limit?: number; offset?: number } = {}
): QualHistoryPage {
  need(READ)
  const limit = q.limit ?? QUAL_HISTORY_LIMIT_DEFAULT
  const offset = q.offset ?? 0
  if (!Number.isInteger(limit) || limit < 1 || limit > QUAL_HISTORY_LIMIT_MAX)
    throw apiError(422, [
      {
        loc: ['query', 'limit'],
        type: 'value_error',
        code: 'value_error',
        msg: 'limit: 1-200',
        ctx: { min: 1, max: QUAL_HISTORY_LIMIT_MAX },
      },
    ])
  if (!Number.isInteger(offset) || offset < 0)
    throw apiError(422, [
      {
        loc: ['query', 'offset'],
        type: 'value_error',
        code: 'value_error',
        msg: 'offset: >= 0',
        ctx: { min: 0 },
      },
    ])
  findQ(qualId)
  const rows = store.log
    .filter((l) => l.qual_id === qualId)
    .map((l, i) => ({ l, i }))
    // at 倒序；同一时刻后写的在前
    .sort((a, b) => b.l.at.localeCompare(a.l.at) || b.i - a.i)
    .map(({ l }) => l)
  return { rows: rows.slice(offset, offset + limit) }
}

/** 每日过期扫描（Q6-1）：到期次日（站点时区）写 expired 履历并发事件，按 (qual_id, expires_on) 去重；is_active 不变。 */
export function mockQualExpiryScan(): number {
  const today = siteToday(mockNow())
  let n = 0
  for (const x of store.q) {
    if (!x.expires_on || x.expires_on >= today) continue
    const dup = store.log.some(
      (l) =>
        l.qual_id === x.id &&
        l.action === 'expired' &&
        l.after?.expires_on === x.expires_on
    )
    if (dup) continue
    record(x, 'expired', null, { expires_on: x.expires_on }, {}, 'system', {
      expires_on: x.expires_on,
    })
    n++
  }
  return n
}

/**
 * 进站检查（D74 / Q6-1）：同一人同一工序，「工序+设备类型」优先于「只按工序」；
 * 只按 expires_on（站点日期，当天有效）判断过期，过期 409 check_blocked、overridable=false，
 * results[] 的资质项 ctx 带 expires_on；停用另算（不在本 mock 的过期分支里）。通过返回 null。
 */
export function mockTrackInQualCheck(
  username: string,
  operationId: string,
  equipmentTypeId?: string | null
) {
  const today = siteToday(mockNow())
  const mine = store.q.filter(
    (x) =>
      x.username === username && x.operation_id === operationId && x.is_active
  )
  const pick =
    (equipmentTypeId &&
      mine.find((x) => x.equipment_type_id === equipmentTypeId)) ||
    mine.find((x) => !x.equipment_type_id) ||
    null
  if (!pick) return null
  if (!pick.expires_on || pick.expires_on >= today) return null
  const ctx = {
    reason: 'expired',
    qual_id: pick.id,
    expires_on: pick.expires_on,
    warn_days: qualMockWarnDays(),
  }
  return apiError(409, {
    code: 'check_blocked',
    message: 'operator qualification expired',
    overridable: false,
    results: [
      {
        check_type: QUAL_CHECK_TYPE,
        result: 'block',
        severity: 'block',
        overridable: false,
        applicable: true,
        message: 'operator qualification expired',
        ctx,
      },
    ],
  })
}

/** 资质写接口（mock；真实接口走通用 CRUD）。key 必填（B6 验收要点）。 */
export interface QualWriteApi {
  grant: (input: QualInput & QualReason, key: string) => Promise<OperatorQual>
  update: (
    id: string,
    body: Partial<QualInput> & QualReason,
    key: string
  ) => Promise<OperatorQual>
  remove: (id: string) => Promise<void>
}

export const mockQualWriteApi: QualWriteApi = {
  grant: (input, key) =>
    later(() => {
      need(WRITE)
      return withKey(
        key,
        sigOf('grant', input),
        () => mockGrant(input),
        () =>
          qualBodyCheck({ ...input, is_active: undefined, expires_on: null })
      )
    }),
  update: (id, body, key) =>
    later(() => {
      need(WRITE)
      return withKey(
        key,
        sigOf(`update:${id}`, body),
        () => mockUpdate(id, body),
        () => qualBodyCheck(body)
      )
    }),
  remove: (id) =>
    later(() => {
      need(WRITE)
      mockRemove(id)
    }),
}

export const mockQualHistoryApi: QualHistoryApi = {
  history: (qualId, q) => later(() => mockHistory(qualId, q)),
}

/** 是否使用 mock（后端 B6 就绪后设 VITE_QUAL_HISTORY_MOCK=0）。 */
export const QUAL_HISTORY_MOCK = import.meta.env.VITE_QUAL_HISTORY_MOCK !== '0'
export const qualHistoryApi: QualHistoryApi = QUAL_HISTORY_MOCK
  ? mockQualHistoryApi
  : httpQualHistoryApi

resetQualHistoryMock()
