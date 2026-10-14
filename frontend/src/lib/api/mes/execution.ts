/** MES 批次执行：阶段作业、检查、Hold、拆合批。 */
import type { StageWarning } from '@/features/mes/execution/over-consumption'
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
  /** 附加数据（如 eqp_wait_qual 的 `{equipment, task_id}`） */
  data?: Record<string, unknown> | null
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
  /** 批次状态（N6；旧版接口无此字段） */
  lot_status?: string | null
  /** D20：Q-Time 自动 Hold 的规则、起止工步与超时秒数（手动 Hold / 旧记录为 null 或缺失） */
  qtime_rule_id?: string | null
  qtime_from_step_id?: string | null
  qtime_to_step_id?: string | null
  qtime_overdue_seconds?: number | null
  qtime_from_step_name?: string | null
  qtime_to_step_name?: string | null
}
/** 追溯对象类型。 */
export type TraceKind =
  | 'lot'
  | 'wafer'
  | 'equipment'
  | 'material_lot'
  | 'customer_lot'
/** 追溯行（各列按场景出现）。 */
export type TraceRow = Record<string, unknown>
/** 追溯结果。 */
export interface TraceResult {
  kind: TraceKind
  /** 批次 / 晶圆带客户信息（B7）；客户批号查询时只有 `customer_lot_no` */
  target: {
    id?: string
    code?: string
    lot?: string
    lot_id?: string
    customer_lot_no?: string | null
    ownership?: string | null
    customer?: string | null
    customer_name?: string | null
  }
  backward?: {
    lots: TraceRow[]
    steps: TraceRow[]
    materials: TraceRow[]
    /** 单位转换的位置映射（B5）：子批位置 ← 母批 / 母晶圆 / die 坐标 */
    origins?: TraceRow[]
  }
  forward?: { lots: TraceRow[]; origins?: TraceRow[]; dies?: TraceRow[] }
  lots?: TraceRow[]
}
/** 按客户批号追溯：每个匹配批次带客户信息和各自的正反向追溯（kind=customer_lot）。 */
export interface CustomerLotTrace {
  /** 9c5e568 样例中不带 lot_id，以 lot_no 兜底作行键 */
  lot_id?: string
  lot_no: string
  lot_status: string
  customer_lot_no: string | null
  ownership: string | null
  customer: string | null
  customer_name?: string | null
  backward?: { lots: TraceRow[]; steps: TraceRow[]; materials: TraceRow[] }
  forward?: { lots: TraceRow[] }
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
  step_id: string | null
  lot_status: string
  equipment_id: string | null
  carrier: string | null
  qty: number
  priority: string | null
  priority_level: number | null
  priority_color: string | null
  hot: boolean
  on_hold: boolean
  qtime_remaining: number | null
  hours: number | null
}
/** 载具总览行。 */
export interface CarrierRow {
  id: string
  code: string
  carrier_type: string | null
  status: string
  lot_id: string | null
  lot: string | null
  /** 载具内非终态批次的状态；空载具为 null（旧版接口无此字段） */
  lot_status?: string | null
  wafers: number
  capacity: number | null
  use_count: number
  max_uses: number | null
  last_cleaned_at: string | null
  clean_due_at: string | null
  due_state: 'ok' | 'warn' | 'overdue'
}
/** 良率分组维度。 */
export type YieldGroup = 'operation' | 'product' | 'lot'
/** 良率统计行。 */
export interface YieldRow {
  key: string
  name: string
  good: number
  scrap: number
  yield: number | null
}
/** 报废原因帕累托项。 */
export interface ParetoRow {
  reason: string
  name: string
  qty: number
  pct: number
  cum_pct: number
}
/** 良率统计结果。 */
export interface YieldReport {
  rows: YieldRow[]
  pareto: ParetoRow[]
  total: { good: number; scrap: number; yield: number | null }
}
/** 批量作业阶段。 */
export type BatchStage = 'track_in' | 'track_out'
/** 批量作业候选（设备上的批次、腔体与配方）。 */
export interface BatchCandidates {
  lots: QueueRow[]
  chambers: EqpOpt[]
  recipes: (Opt & { version: number })[]
}
/** 批量作业单批结果。 */
export interface BatchItem {
  lot_id: string
  code: string
  ok?: boolean
  results?: CheckResult[]
  error?: unknown
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
  relation: 'split' | 'merge' | 'transform'
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
  equipment?: (EqpOpt & { chambers: EqpOpt[] })[]
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
/** 设备 / 腔体候选（含当前 E10 状态）。 */
export type EqpOpt = Opt & {
  state: string | null
  category: string | null
  color: string | null
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
  /** 选定的腔体 */
  chamber_ids?: string[]
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
  future_hold?: { id: string; reason: string; comment: string | null }[]
  oos_action?: string | null
  e10?: Record<string, unknown> | null
  next_step?: { id: string; seq: number } | null
  /** 出站提示（F4：bom_over_consumption 只提示、不拦截） */
  warnings?: StageWarning[]
}

/** 十进制数量：P1 新接口按定点字符串返回（D50），老接口为数字；只用 `lib/decimal` 显示。 */
export type DecimalValue = number | string
/** 批次 BOM 用量的一条明细（`GET /mes/exec/lots/{id}/bom-usage`）。 */
export interface BomUsageLine {
  bom_line_id: string
  line_no: number
  material: string | null
  operation: string | null
  uom: string | null
  per_basis: string
  basis: DecimalValue
  planned: DecimalValue
  actual: DecimalValue
  over: boolean
  excess: DecimalValue
  unconverted?: unknown
}
/** 批次 BOM 用量总览（D50：basis / planned / actual / excess 为定点字符串）。 */
export interface BomUsage {
  lot: string
  scope: string
  bom_id: string | null
  bom_version: number | null
  basis: DecimalValue
  lines: BomUsageLine[]
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

/** 单位转换类型（B5 / F8）。 */
export type TransformType = 'dicing' | 'die_attach' | 'singulation'
export type TrackUnitKind = 'die' | 'strip' | 'package' | 'unit'
/** 单位转换请求（严格载荷，未知字段 422）。 */
export interface TransformBody {
  transform_type: TransformType
  input_lot_ids: string[]
  outputs: {
    product_id: string
    route_id: string
    track_unit_kind: TrackUnitKind
    qty?: number
    sources: { wafer_id: string; qty: number }[]
  }[]
  manual_good?: { wafer_id: string; good_qty: number; fail_qty?: number }[]
  reason_id?: string
  comment?: string
}
/** 转换预览：逐片晶圆良品数与分配、输出数量、提示（不写库）。 */
export interface TransformPreview {
  inputs: {
    lot: string
    wafer: string
    wafer_id: string
    good_source: 'map' | 'manual' | 'gross_die'
    total_qty: number
    good_qty: number
    fail_qty: number
    excluded_qty: number
    allocated_qty: number
    substrate_map_id: string | null
    map_version: number | null
  }[]
  outputs: {
    product_id: string
    route_id: string
    track_unit_kind: TrackUnitKind
    qty: number
    die_qty: number
  }[]
  warnings: { code: string; message?: string; wafer?: string }[]
}
/** 按 bin 拆批请求（B8 / F7；不给 outputs 时每个 bin 一个子批）。 */
export interface BinSplitBody {
  input_lot_ids: string[]
  outputs?: { bin_codes: string[]; product_id?: string; route_id?: string }[]
  manual_bins?: {
    wafer_id: string
    bins: { bin_code: string; qty: number }[]
  }[]
  reason_id?: string
  comment?: string
}
/** 按 bin 拆批预览：逐片晶圆各 bin 数量与守恒、各子批数量（不写库）。 */
export interface BinSplitPreview {
  inputs: {
    lot: string
    wafer: string
    wafer_id: string
    bin_source: 'map' | 'manual'
    substrate_map_id: string | null
    map_version: number | null
    bin_set: { code: string; version: number } | null
    total_qty: number
    excluded_qty: number
    bin_counts: Record<string, number>
    split_counts: Record<string, number>
    children_qty: number
    conserved: boolean
  }[]
  outputs: {
    bin_code: string
    bin_codes: string[]
    product_id: string
    route_id: string | null
    qty: number
  }[]
  warnings: { code: string; message?: string; wafer?: string }[]
}
/** 撤销转换结果（P2 / 86ca4a1）：恢复后的母批与被删除的子批编码。 */
export interface TransformUndoResult {
  transform_id: string
  transform_type: string
  parents: MesRow[]
  removed_children: string[]
}
/** 撤销被拒（409 transform_undo_blocked）时每个批次的原因。 */
export type UndoBlockReason =
  | 'lot_status'
  | 'on_hold'
  | 'has_transactions'
  | 'has_descendants'
  | 'parent_status'
/** 转换 / 按 bin 拆批提交结果。 */
export interface TransformResult {
  transform: MesRow
  children: MesRow[]
  warnings: { code: string; message?: string; wafer?: string }[]
}

export const execApi = {
  /** 良率统计与报废帕累托。 */
  yieldReport: (p: {
    date_from?: string
    date_to?: string
    group: YieldGroup
  }) =>
    http
      .get<YieldReport>('/mes/exec/reports/yield', { params: p })
      .then((r) => r.data),
  /** 晶圆整理（Sorter）：重排槽位，可移入另一载具。 */
  sortWafers: (
    lotId: string,
    body: {
      slots: { wafer_id: string; slot: number }[]
      carrier_id?: string | null
      override?: boolean
      override_reason?: string
    }
  ) => http.post(`/mes/exec/lots/${lotId}/sort`, body).then((r) => r.data),
  /** 载具总览。 */
  carrierBoard: () =>
    http
      .get<{ data: CarrierRow[] }>('/mes/exec/carriers/board')
      .then((r) => r.data.data),
  /** 清洗载具。 */
  carrierClean: (id: string, comment?: string) =>
    http
      .post(`/mes/exec/carriers/${id}/clean`, { comment })
      .then((r) => r.data),
  /** 批次换载具。 */
  changeCarrier: (lotId: string, carrierId: string, comment?: string) =>
    http
      .post(`/mes/exec/lots/${lotId}/carrier`, {
        carrier_id: carrierId,
        comment,
      })
      .then((r) => r.data),
  /** 批量作业候选批次。 */
  batchCandidates: (stage: BatchStage, equipmentId: string) =>
    http
      .get<BatchCandidates>(`/mes/exec/batch/${stage}/candidates`, {
        params: { equipment_id: equipmentId },
      })
      .then((r) => r.data),
  /** 批量 Track In / Track Out。 */
  batchStage: (stage: BatchStage, lotIds: string[], body: StageBody) =>
    http
      .post<{
        items: BatchItem[]
      }>(`/mes/exec/batch/${stage}`, { lot_ids: lotIds, ...body })
      .then((r) => r.data.items),
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
  /** Hold 列表（服务端分页 / 搜索 / 筛选）；Hold 时间范围映射为 date_from / date_to。 */
  holds: (p: Record<string, string | number | undefined>) => {
    const { held_at_from, held_at_to, ...rest } = p
    return http
      .get<{ data: HoldRow[]; count: number }>('/mes/exec/holds', {
        params: { ...rest, date_from: held_at_from, date_to: held_at_to },
      })
      .then((r) => r.data)
  },
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
  /** 单位转换预览（mes.exec:transform；不写库）。 */
  transformPreview: (body: TransformBody) =>
    http
      .post<TransformPreview>('/mes/exec/transform/preview', body)
      .then((r) => r.data),
  /** 单位转换提交：母批 → converted，生成子批。 */
  transform: (body: TransformBody) =>
    http.post<TransformResult>('/mes/exec/transform', body).then((r) => r.data),
  /** 撤销单位转换 / 按 bin 拆批（mes.exec:transform；子批未动过才可撤销，否则 409）。 */
  transformUndo: (
    transformId: string,
    body: { reason_id?: string; comment?: string }
  ) =>
    http
      .post<TransformUndoResult>(
        `/mes/exec/transform/${transformId}/undo`,
        body
      )
      .then((r) => r.data),
  /** 按 bin 拆批预览（mes.exec:transform；不写库）。 */
  binSplitPreview: (body: BinSplitBody) =>
    http
      .post<BinSplitPreview>('/mes/exec/bin-split/preview', body)
      .then((r) => r.data),
  /** 按 bin 拆批提交：母批 → converted，子批带 bin_code。 */
  binSplit: (body: BinSplitBody) =>
    http.post<TransformResult>('/mes/exec/bin-split', body).then((r) => r.data),
  /** 批次 BOM 用量（计划 / 实际 / 超量；需 mes.exec:read，不存在 404）。 */
  bomUsage: (lotId: string) =>
    http.get<BomUsage>(`/mes/exec/lots/${lotId}/bom-usage`).then((r) => r.data),
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
  priority: (
    id: string,
    body: {
      priority_id: string
      comment?: string
      override?: boolean
      override_reason?: string
    }
  ) =>
    http
      .post<StageResult>(`/mes/exec/lots/${id}/priority`, body)
      .then((r) => r.data),
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
