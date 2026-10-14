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
import { apiError, setMockReplayed } from './mock-utils'

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
  /** 后端履历行不返回 qual_id（mock 内部用） */
  qual_id?: string
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
/** mock 的 operator_qual 原因码 / 租户用户；null = 不校验（默认） */
let mockReasons: string[] | null = null
let mockUsers: string[] | null = null
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
  mockReasons = null
  mockUsers = null
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
/** 测试用：启用 invalid_reason / user_not_found 校验。 */
export const setQualMockReasons = (v: string[] | null) => {
  mockReasons = v
}
export const setQualMockUsers = (v: string[] | null) => {
  mockUsers = v
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

/** 写入意图（仅由请求体判断，供请求体 422 使用，先于 404）。
 *  D88：请求体里只要带了 expires_on（含 null = 改为永久、含缩短）就按延期处理，必须有批准人。 */
export type QualIntent = 'deactivate' | 'renew' | 'other'
const hasExpires = (body: object) =>
  'expires_on' in body &&
  (body as { expires_on?: unknown }).expires_on !== undefined
export function qualIntent(body: Partial<QualInput> & QualReason): QualIntent {
  if (body.is_active === false) return 'deactivate'
  if (hasExpires(body)) return 'renew'
  return 'other'
}

type ErrItem = {
  loc: string[]
  type: string
  code: string
  msg: string
  ctx?: Record<string, unknown>
}
const item = (
  loc: string,
  type: string,
  msg: string,
  ctx?: Record<string, unknown>
): ErrItem => ({ loc: ['body', loc], type, code: type, msg, ctx })
const same = (a: unknown, b: unknown) =>
  typeof a === 'string' &&
  typeof b === 'string' &&
  a.trim().toLowerCase() === b.trim().toLowerCase()

/**
 * 请求体 422（B6 40e4342 check_extras 同序）：
 * 1. PATCH 停用 + expires_on → conflicting_fields；
 * 2. PATCH 停用缺 reason_id / comment，带 expires_on 缺 reason_id / comment / approved_by → missing（一次全报）；
 * 3. value_error 一次全报：comment > 300（max_length）、reason_id 不是启用的 operator_qual 原因（invalid_reason）、
 *    approved_by 不是本租户用户（user_not_found）；
 * 4. approved_by = 发请求的人（不分大小写）→ self_approval。POST 授予不要求附加字段。
 */
export function qualBodyCheck(
  body: Partial<QualInput> & QualReason,
  method: 'POST' | 'PATCH' = 'PATCH'
) {
  if (method === 'PATCH' && body.is_active === false && hasExpires(body))
    throw valueErr(
      'is_active',
      'deactivate and renew cannot be combined in one request',
      {
        reason: 'conflicting_fields',
        fields: ['is_active', 'expires_on'],
      }
    )
  if (method === 'PATCH') {
    const need: (keyof QualReason)[] = []
    if (body.is_active === false) need.push('reason_id', 'comment')
    if (hasExpires(body)) need.push('reason_id', 'comment', 'approved_by')
    const miss = [...new Set(need)].filter((k) => blank(body[k]))
    if (miss.length)
      throw apiError(
        422,
        miss.map((k) => item(k, 'missing', 'Field required'))
      )
  }
  const errs: ErrItem[] = []
  if (
    body.comment != null &&
    (typeof body.comment !== 'string' ||
      [...body.comment].length > QUAL_COMMENT_MAX)
  )
    errs.push(
      item(
        'comment',
        'value_error',
        `comment: string of at most ${QUAL_COMMENT_MAX} characters`,
        { reason: 'max_length', max_length: QUAL_COMMENT_MAX }
      )
    )
  if (
    body.reason_id != null &&
    mockReasons &&
    !mockReasons.includes(String(body.reason_id))
  )
    errs.push(
      item(
        'reason_id',
        'value_error',
        'reason_id: must be an active reason code of type operator_qual',
        { reason: 'invalid_reason' }
      )
    )
  const ab = body.approved_by
  if (
    ab != null &&
    (typeof ab !== 'string' ||
      [...ab].length > QUAL_APPROVED_BY_MAX ||
      (mockUsers && !mockUsers.some((u) => same(u, ab))))
  )
    errs.push(
      item(
        'approved_by',
        'value_error',
        'approved_by: not a user of this tenant',
        {
          reason: 'user_not_found',
        }
      )
    )
  if (errs.length) throw apiError(422, errs)
  if (!blank(ab) && same(ab, mockUser))
    throw valueErr(
      'approved_by',
      'approved_by must not be the requesting user',
      {
        reason: 'self_approval',
      }
    )
}

/** 404 之后、409 之前（D85）：批准人不能是持有人；POST 时 row 为请求体。 */
function holderCheck(body: QualReason, holder: string) {
  if (!blank(body.approved_by) && same(body.approved_by, holder))
    throw valueErr(
      'approved_by',
      'approved_by must not be the qualification holder',
      { reason: 'holder_approval' }
    )
}

function withKey<T>(key: string, sig: string, f: () => T, pre: () => void): T {
  setMockReplayed(false)
  if (!key) throw missing('Idempotency-Key', 'header')
  pre()
  const hit = idem.get(key)
  if (hit) {
    if (hit.sig !== sig)
      throw apiError(422, {
        code: 'idempotency_key_reused',
        message: 'Idempotency-Key reused with a different body',
      })
    setMockReplayed(true) // D86 补充二：回放带 Idempotent-Replayed
    return structuredClone(hit.out) as T
  }
  const out = f()
  // D86：只缓存 2xx；f() 抛出的 4xx 不进缓存，同 key 重发重新校验
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
  holderCheck(input, input.username)
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
  // D85：批准人 = 持有人 → 422 holder_approval（404 之后、409 之前）
  holderCheck(body, x.username)
  // 40e4342：已停用再停用、无实际变更 → 200 原样返回，不写履历（classify 为 None）
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
    // 40e4342 classify/_later：原来有到期日且新到期日更晚（或改为永久）才算 renewed；
    // 缩短、或原来永久改为有期限都记 changed（D88：同样要批准人）
    changed.includes('expires_on') &&
    prev.expires_on != null &&
    (x.expires_on == null || x.expires_on > prev.expires_on)
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

function mockRemove(id: string): never {
  const x = findQ(id)
  // D84 / 架构师：资质只能停用；DELETE 通过 D81 校验后总是 409 referenced，顶层 ref_type / ref_count
  throw apiError(409, {
    code: 'referenced',
    message: 'qualification cannot be deleted; deactivate it instead',
    ref_type: 'operator_qual_log',
    ref_count: store.log.filter((l) => l.qual_id === x.id).length,
  })
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
        ctx: { min: 0, max: 10 ** 9 },
      },
    ])
  // 40e4342：履历 404 为对象 {code:'not_found'}
  if (!store.q.some((y) => y.id === qualId))
    throw apiError(404, {
      code: 'not_found',
      message: 'operator qualification not found',
    })
  const rows = store.log
    .filter((l) => l.qual_id === qualId)
    .map((l, i) => ({ l, i }))
    // at 倒序；同一时刻后写的在前
    .sort((a, b) => b.l.at.localeCompare(a.l.at) || b.i - a.i)
    .map(({ l }) => l)
  // 后端行不带 qual_id
  return {
    rows: rows
      .slice(offset, offset + limit)
      .map(({ qual_id: _q, ...rest }) => rest),
  }
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
  // 40e4342 registry：顶层 ctx 只有 {qual_id, expires_on}；data 另带 user / operation / reason / warn_days
  const ctx = { qual_id: pick.id, expires_on: pick.expires_on }
  const data = {
    user: username,
    operation: operationId,
    warn_days: qualMockWarnDays(),
    reason: 'expired',
    expires: pick.expires_on,
    expires_on: pick.expires_on,
    qual_id: pick.id,
    ctx,
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
        data,
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
  /** QA P2-2：DELETE 也必须带 key */
  remove: (id: string, key: string) => Promise<void>
}

export const mockQualWriteApi: QualWriteApi = {
  grant: (input, key) =>
    later(() => {
      need(WRITE)
      return withKey(
        key,
        sigOf('grant', input),
        () => mockGrant(input),
        () => qualBodyCheck(input, 'POST')
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
  // D81：403 → 缺 key 422 → 404 → 409 referenced；D86：4xx 不缓存，同 key 重发重新校验，无回放
  remove: (id, key) =>
    later(() => {
      need(WRITE)
      withKey(
        key,
        sigOf(`remove:${id}`, {}),
        () => {
          mockRemove(id)
          return null
        },
        () => {}
      )
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
