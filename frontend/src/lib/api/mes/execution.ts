/** MES lot execution: stages, checks, holds, split/merge. */
import { http } from '../client'
import type { MesRow } from './common'

export type ExecStage = 'move_in' | 'track_in' | 'track_out' | 'move_out'
export const EXEC_STAGES: ExecStage[] = [
  'move_in',
  'track_in',
  'track_out',
  'move_out',
]
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
export interface Opt {
  id: string
  code: string
  name?: string
  [k: string]: unknown
}
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
export interface ExecUnit {
  id: string
  code: string
  slot: number | null
  status: string
  unit_kind: string
  rework_count: number
}
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
export interface PrioRef {
  id: string
  code: string
  name: string
  level: number
  color: string | null
}
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
export interface SplitChild {
  unit_ids?: string[]
  qty?: number
  carrier_id?: string | null
}
export interface SmBody {
  comment?: string
  override?: boolean
  override_reason?: string
  preview?: boolean
}
export interface SmResult {
  results: CheckResult[]
  children?: { id: string; code: string; qty: number; units: string[] }[]
  merged?: { code: string; qty: number }[]
  lot?: MesRow
}
export interface ExecContext {
  lot: MesRow
  sm?: SmContext
  next_stage: ExecStage | null
  tracking_level: 'wafer' | 'unit' | 'quantity'
  units: ExecUnit[]
  holds: MesRow[]
  reasons: Record<'hold' | 'release' | 'scrap' | 'rework', Opt[]>
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
export interface StageBody {
  equipment_id?: string | null
  recipe_id?: string | null
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
export interface StageResult {
  lot: MesRow
  results: CheckResult[]
  auto?: { stage: ExecStage; ok: boolean; error?: unknown }[]
  qtime?: string
  oos_action?: string | null
  e10?: Record<string, unknown> | null
  next_step?: { id: string; seq: number } | null
}

export const execApi = {
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

/** Check results of a blocked stage (409 check_blocked), else null. */
export function blockedResults(err: unknown): CheckResult[] | null {
  const r = (
    err as { response?: { status?: number; data?: { detail?: unknown } } }
  )?.response
  const d = r?.data?.detail as { code?: string; results?: CheckResult[] }
  return r?.status === 409 && d?.code === 'check_blocked'
    ? (d.results ?? [])
    : null
}
