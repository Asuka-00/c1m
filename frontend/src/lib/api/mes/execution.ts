/** MES 批次执行：阶段作业、检查、Hold、拆合批。 */
import { http } from '../client'
import type { MesRow } from './common'

/** 执行阶段。 */
export type ExecStage = 'move_in' | 'track_in' | 'track_out' | 'move_out'
/** 四个执行阶段（按顺序）。 */
export const EXEC_STAGES: ExecStage[] = [
  'move_in',
  'track_in',
  'track_out',
  'move_out',
]
/** 一条检查结果（规则、严重度、结果、是否可放行等）。 */
export interface CheckResult {
  check_type: string
  rule_id: string | null
  rule_code: string | null
  rule_name: string | null
  plan_code: string | null
  severity: 'block' | 'warn'
  result: 'pass' | 'warn' | 'block' | 'overridden'
  applicable: boolean
  message: string
  overridable: boolean
}
/** 简单选项（id + 标签）。 */
export interface Opt {
  id: string
  code: string
  name?: string
  [k: string]: unknown
}
/** DC 量测项（含规格上下限与抽样单元）。 */
export interface DcItem {
  measurement_item_id: string
  code: string
  name: string
  meas_type: string
  lsl: number | null
  usl: number | null
  target: number | null
  sites: number | null
  oos_action: string
}
/** 批次单元（晶圆 / 序列号）。 */
/** WIP 看板汇总。 */
export interface WipSummary {
  total_lots: number
  total_qty: number
  on_hold: number
  by_status: { status: string; lots: number; qty: number }[]
  by_step: {
    route: string | null
    step_seq: number | null
    operation: string | null
    lots: number
    qty: number
    on_hold: number
  }[]
  by_product: {
    product_id: string | null
    product: string | null
    lots: number
    qty: number
  }[]
  aging: {
    id: string
    lot: string
    status: string
    on_hold: boolean
    step_seq: number | null
    qty: number
    since: string | null
    hours: number | null
  }[]
}
/** 产出日报行。 */
export interface DailyOutput {
  day: string
  moves: number
  move_qty: number
  scrap_qty: number
  completed: number
}
/** 设备 OEE 行（无法计算的指标为 null）。 */
export interface OeeRow {
  id: string
  equipment: string
  name: string
  workcenter: string | null
  hours: Record<string, number>
  loading_h: number
  prd_h: number
  availability: number | null
  performance: number | null
  quality: number | null
  oee: number | null
  good: number
  scrap: number
  uph_missing: boolean
}
/** 生效中的 Hold 行。 */
export interface OeeTrendRow {
  day: string
  availability: number | null
  quality: number | null
  oee: number | null
  loading_h: number
}
/** Hold 记录（Hold 管理页：生效中 / 已解除）。 */
export interface HoldRow {
  id: string
  lot_id: string
  lot: string
  product: string | null
  step_seq: number | null
  reason: string | null
  reason_name: string | null
  source: string
  hold_type: string
  held_at: string | null
  held_by: string | null
  is_active: boolean
  hours: number | null
  comment: string | null
  released_at: string | null
  released_by: string | null
  release_reason: string | null
  release_comment: string | null
}
/** 追溯对象类型。 */
export type TraceKind = 'lot' | 'wafer' | 'equipment' | 'material_lot'
/** 追溯行（各列按场景出现）。 */
export type TraceRow = Record<string, unknown>
/** 追溯结果。 */
export interface TraceResult {
  kind: TraceKind
  target: { id: string; code: string; lot?: string; lot_id?: string }
  backward?: { lots: TraceRow[]; steps: TraceRow[]; materials: TraceRow[] }
  forward?: { lots: TraceRow[] }
  lots?: TraceRow[]
}
/** Q-Time 监控行。 */
export interface QtimeRow {
  lot_id: string
  lot: string
  on_hold: boolean
  product: string | null
  route: string | null
  step_seq: number
  rule: string
  since: string
  minutes: number
  max_minutes: number | null
  remaining: number | null
  exceeded: boolean
  warn: boolean
  warn_minutes: number | null
  action: string
}
/** 派工队列行。 */
export interface QueueRow {
  id: string
  code: string
  product: string | null
  step_seq: number | null
  operation: string | null
  operation_name: string | null
  lot_status: string
  qty: number
  priority: string | null
  priority_level: number | null
  priority_color: string | null
  on_hold: boolean
  qtime_remaining: number | null
  hours: number | null
}
/** 首页概览指标。 */
export interface HomeSummary {
  wip_lots: number
  wip_qty: number
  on_hold: number
  qtime_warn: number
  qtime_exceeded: number
  equipment: { category: string; color: string | null; count: number }[]
  pm_due: number
  pm_warn: number
  track_outs_today: number
}
export interface ExecUnit {
  id: string
  code: string
  slot: number | null
  status: string
  unit_kind: string
  rework_count: number
}
/** 谱系关系（拆批 / 合批）。 */
export interface GenealogyLink {
  relation: 'split' | 'merge'
  parent_id: string
  parent: string
  child_id: string
  child: string
  qty: number
  units: string[]
  at: string | null
  user: string | null
}
/** 优先级引用。 */
export interface PrioRef {
  id: string
  code: string
  name: string
  level: number
  color: string | null
}
/** 拆合批上下文（规则摘要、可拆 / 可合、候选批次）。 */
export interface SmContext {
  priority: PrioRef | null
  rule: {
    code: string
    allow_split: boolean
    allow_merge: boolean
    max_children: number
    min_qty: number
    child_id_mode: string
    merge_same_wo: boolean
    children: number
  } | null
  allowed: boolean
  candidates: {
    id: string
    code: string
    qty: number
    on_hold: boolean
    priority: PrioRef | null
    problems: string[]
  }[]
  genealogy: GenealogyLink[]
}
/** 拆批的一个子批定义（单元或数量、载具）。 */
export interface SplitChild {
  unit_ids?: string[]
  qty?: number
  carrier_id?: string | null
}
/** 拆批 / 合批请求体。 */
export interface SmBody {
  comment?: string
  override?: boolean
  override_reason?: string
  preview?: boolean
}
/** 拆批 / 合批结果。 */
export interface SmResult {
  results: CheckResult[]
  children?: { id: string; code: string; qty: number; units: string[] }[]
  merged?: { code: string; qty: number }[]
  lot?: MesRow
}
/** 批次操作台上下文（`GET /mes/exec/lots/{id}/context`）。 */
export interface ExecContext {
  lot: MesRow
  sm?: SmContext
  next_stage: ExecStage | null
  tracking_level: 'wafer' | 'unit' | 'quantity'
  units: ExecUnit[]
  holds: MesRow[]
  reasons: Record<
    'hold' | 'release' | 'scrap' | 'rework' | 'jump' | 'bonus',
    Opt[]
  >
  /** 当前流程的工序工步（跳站目标） */
  route_steps?: { id: string; seq: number; operation: string | null }[]
  stack: { kind: string; route_id: string; step_id: string }[]
  step?: {
    id: string
    seq: number
    route: string
    route_id: string
    operation: Opt | null
    branch_to_seq: number | null
    branch_condition: string | null
    rework_route: string | null
    rework_return: string | null
    auto: Record<ExecStage, boolean>
    is_last: boolean
  }
  equipment?: (Opt & {
    state: string | null
    category: string | null
    color: string | null
  })[]
  recipes?: (Opt & { version: number; status: string })[]
  reticles?: (Opt & { status: string })[]
  tools?: {
    fixture: Opt | null
    options: (Opt & {
      status: string
      usage: number
      max: number | null
      expiry: string | null
      warn_pct: number
    })[]
  }[]
  materials?: {
    material_id: string
    material: string
    need: number
    basis: string
    uom: string | null
    options: (Opt & {
      qty: number
      expiry: string | null
      location: string | null
    })[]
  }[]
  dc?: {
    sampled: boolean
    rule?: string | null
    dc_plan?: string
    unit_ids?: string[]
    items: DcItem[]
    message: string
  }
  qtime?: {
    rule: string
    minutes: number
    min: number | null
    max: number | null
    exceeded: boolean
    too_early: boolean
  }[]
  exec_ctx: Record<string, unknown>
}
/** 阶段作业请求体（设备、配方、工具、物料、DC、报废 / 返工、放行等）。 */
export interface StageBody {
  equipment_id?: string | null
  recipe_id?: string | null
  /** 设备上报 / 扫描的设备端配方名 */
  eqp_recipe?: string | null
  reticle_id?: string | null
  carrier_id?: string | null
  tool_ids?: string[]
  material_lot_ids?: string[]
  dc?: {
    measurement_item_id: string
    unit_id?: string | null
    site_no?: number
    value: number
  }[]
  scrap?: { reason_id: string; unit_id?: string; qty?: number }[]
  rework_units?: { reason_id: string; unit_id: string }[]
  branch?: boolean
  rework?: boolean
  override?: boolean
  override_reason?: string
}
/** 阶段作业结果（批次、检查结果、事件、自动阶段）。 */
export interface StageResult {
  lot: MesRow
  results: CheckResult[]
  auto?: { stage: ExecStage; ok: boolean; error?: unknown }[]
  qtime?: string
  oos_action?: string | null
  e10?: Record<string, unknown> | null
  next_step?: { id: string; seq: number } | null
}

/** 批次执行接口：上下文、阶段作业、检查预览、Hold、拆合批、履历。 */
/** 晶圆图中的一片晶圆。 */
export interface WaferCell {
  id: string
  code: string
  status: string
  rework_count?: number
}
/** 晶圆图：按槽位排列的晶圆。 */
export interface WaferMap {
  lot: string
  carrier: string | null
  capacity: number
  slots: { slot: number; wafer: WaferCell | null }[]
  /** 无槽位的单元 */
  units: WaferCell[]
}

export const execApi = {
  /** 批次晶圆图。 */
  waferMap: (lotId: string) =>
    http.get<WaferMap>(`/mes/exec/lots/${lotId}/wafer-map`).then((r) => r.data),
  /** 晶圆级履历（含所在批次的批次级记录）。 */
  waferHistory: (waferId: string) =>
    http
      .get<{ data: MesRow[] }>(`/mes/exec/wafers/${waferId}/history`)
      .then((r) => r.data.data),
  split: (lotId: string, children: SplitChild[], body: SmBody) =>
    http
      .post<SmResult>(`/mes/exec/lots/${lotId}/split`, { children, ...body })
      .then((r) => r.data),
  merge: (lotId: string, source_lot_ids: string[], body: SmBody) =>
    http
      .post<SmResult>(`/mes/exec/lots/${lotId}/merge`, {
        source_lot_ids,
        ...body,
      })
      .then((r) => r.data),
  context: (lotId: string) =>
    http.get<ExecContext>(`/mes/exec/lots/${lotId}`).then((r) => r.data),
  preview: (lotId: string, stage: ExecStage, body: StageBody) =>
    http
      .post<{
        results: CheckResult[]
      }>(`/mes/exec/lots/${lotId}/preview/${stage}`, body)
      .then((r) => r.data),
  stage: (lotId: string, stage: ExecStage, body: StageBody) =>
    http
      .post<StageResult>(`/mes/exec/lots/${lotId}/${stage}`, body)
      .then((r) => r.data),
  /** WIP 看板汇总。 */
  wip: (p: { product_id?: string; lot_type_id?: string; route_id?: string }) =>
    http
      .get<WipSummary>('/mes/exec/reports/wip', { params: p })
      .then((r) => r.data),
  /** OEE 日趋势。 */
  oeeTrend: (p: {
    date_from?: string
    date_to?: string
    workcenter?: string
  }) =>
    http
      .get<{ data: OeeTrendRow[] }>('/mes/exec/reports/oee-trend', {
        params: p,
      })
      .then((r) => r.data.data),
  /** 产出日报。 */
  output: (p: { date_from?: string; date_to?: string }) =>
    http
      .get<{ data: DailyOutput[] }>('/mes/exec/reports/output', { params: p })
      .then((r) => r.data.data),
  /** 设备 OEE。 */
  oee: (p: { date_from?: string; date_to?: string }) =>
    http
      .get<{ data: OeeRow[] }>('/mes/exec/reports/oee', { params: p })
      .then((r) => r.data.data),
  /** Hold 列表：默认生效中，可切换已解除（历史）/ 全部。 */
  holds: (status: 'active' | 'released' | 'all' = 'active') =>
    http
      .get<{ data: HoldRow[] }>('/mes/exec/holds', { params: { status } })
      .then((r) => r.data.data),
  /** 批量释放 Hold。 */
  releaseBatch: (body: {
    hold_ids: string[]
    reason_id: string
    comment?: string
  }) =>
    http
      .post<{
        released: string[]
        failed: { id: string; error: string }[]
      }>('/mes/exec/holds/release-batch', body)
      .then((r) => r.data),
  /** 追溯查询（批次 / 晶圆 / 设备 / 物料批）。 */
  trace: (kind: TraceKind, code: string) =>
    http
      .get<TraceResult>('/mes/exec/trace', { params: { kind, code } })
      .then((r) => r.data),
  /** 派工队列（在制批次，按 Hold / 优先级 / Q-Time / 滞留排序）。 */
  queue: () =>
    http.get<{ data: QueueRow[] }>('/mes/exec/queue').then((r) => r.data.data),
  /** 首页概览指标。 */
  home: () => http.get<HomeSummary>('/mes/exec/home').then((r) => r.data),
  /** Q-Time 监控（等待中批次的计时）。 */
  qtimeMonitor: () =>
    http
      .get<{ data: QtimeRow[] }>('/mes/exec/qtime/monitor')
      .then((r) => r.data.data),
  /** 立即执行 Q-Time 超时扫描（自动 Hold 等处置）。 */
  qtimeSweep: () =>
    http
      .post<{
        checked: number
        actions: { lot: string; action: string }[]
      }>('/mes/exec/qtime/sweep', {})
      .then((r) => r.data),
  /** 在制报废 / 补数。 */
  adjust: (
    id: string,
    body: {
      kind: 'scrap' | 'bonus'
      reason_id: string
      qty?: number
      unit_ids?: string[]
      comment?: string
      override?: boolean
      override_reason?: string
    }
  ) =>
    http
      .post<StageResult>(`/mes/exec/lots/${id}/adjust`, body)
      .then((r) => r.data),
  jump: (
    lotId: string,
    body: {
      to_step_id: string
      reason_id: string
      comment?: string
      override?: boolean
      override_reason?: string
    }
  ) =>
    http
      .post<StageResult>(`/mes/exec/lots/${lotId}/jump`, body)
      .then((r) => r.data),
  hold: (lotId: string, reason_id: string, comment?: string) =>
    http
      .post<MesRow>(`/mes/exec/lots/${lotId}/hold`, { reason_id, comment })
      .then((r) => r.data),
  release: (holdId: string, reason_id?: string | null, comment?: string) =>
    http
      .post<MesRow>(`/mes/exec/holds/${holdId}/release`, {
        reason_id: reason_id || null,
        comment,
      })
      .then((r) => r.data),
}

/** 被阻断阶段的检查结果（409 check_blocked），否则为 null。 */
export function blockedResults(err: unknown): CheckResult[] | null {
  const r = (
    err as { response?: { status?: number; data?: { detail?: unknown } } }
  )?.response
  const d = r?.data?.detail as { code?: string; results?: CheckResult[] }
  return r?.status === 409 && d?.code === 'check_blocked'
    ? (d.results ?? [])
    : null
}
