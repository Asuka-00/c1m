/** 泛半导体单元级作业：单元转换、芯片级晶圆图、Bank 入库 / 领用、NCR / MRB、SPC 控制图。 */
import { saveBlob } from '@/lib/utils'
import { http } from '../client'
import type { MesRow } from './common'
import type { CheckResult } from './execution'

export type UnitKind = 'die' | 'strip' | 'package' | 'unit'
export type DieMapKind = 'cp' | 'aoi' | 'ink'

export interface ConvertBody {
  to_kind: UnitKind
  per_parent?: number
  per_child?: number
  use_map?: boolean
  comment?: string
  override?: boolean
  override_reason?: string
  preview?: boolean
}

export interface ConvertResult {
  results: CheckResult[]
  count: number
  bad_dies: number
  codes?: string[]
}

/** 一颗芯片：[x, y, bin]。 */
export type Die = [number, number, string]

export interface DieMapBrief {
  id: string
  unit?: string
  test_kind?: DieMapKind
  gross: number
  good: number
  yield_pct: number
  is_current?: boolean
  source?: string | null
  at?: string
}

export interface DieMapDetail extends DieMapBrief {
  rows: number
  cols: number
  unit: string
  lot: string
  dies: Die[]
  legend: {
    bin: string
    name: string | null
    color: string | null
    is_good: boolean
    count: number
  }[]
}

export interface NcrDetail {
  ncr: MesRow
  approvals: MesRow[]
  hold_active: boolean
}

export interface SpcPoint {
  lot: string
  lot_id: string
  step_seq: number | null
  mean: number
  n: number
  at: string
  rules: number[]
}

export interface SpcChart {
  item: { id: string; code: string; name: string } | null
  plan: { id: string; code: string } | null
  limits: Record<'usl' | 'lsl' | 'target' | 'ucl' | 'cl' | 'lcl', number | null>
  rules: number[]
  points: SpcPoint[]
}

const post = <T>(url: string, body: unknown) =>
  http.post<T>(url, body).then((r) => r.data)

export const semiApi = {
  /** 整批单元转换（preview 只预检）。 */
  convert: (lotId: string, body: ConvertBody) =>
    post<ConvertResult>(`/mes/exec/lots/${lotId}/convert`, body),
  /** 导入批次内晶圆的芯片级晶圆图。 */
  importDieMaps: (
    lotId: string,
    body: {
      test_kind: DieMapKind
      source?: string
      maps: { unit_code: string; dies: Die[] }[]
    }
  ) => post<{ maps: DieMapBrief[] }>(`/mes/exec/lots/${lotId}/die-maps`, body),
  /** 下载晶圆图 CSV 模板。 */
  dieMapTemplate: async () => {
    const r = await http.get<Blob>('/mes/exec/die-maps/template', {
      responseType: 'blob',
    })
    saveBlob(r.data, 'die_map.csv')
  },
  dieMap: (id: string) =>
    http.get<DieMapDetail>(`/mes/exec/die-maps/${id}`).then((r) => r.data),
  unitDieMaps: (unitId: string) =>
    http
      .get<{ data: DieMapBrief[] }>(`/mes/exec/units/${unitId}/die-maps`)
      .then((r) => r.data.data),
  bankIn: (lotId: string, bankId: string, comment?: string) =>
    post(`/mes/exec/lots/${lotId}/bank-in`, { bank_id: bankId, comment }),
  bankIssue: (body: {
    work_order_id: string
    lots: { lot_id: string; unit_ids?: string[]; qty?: number }[]
    comment?: string
  }) =>
    post<{
      lot: MesRow
      sources: { lot: string; qty: number; left: number }[]
    }>('/mes/exec/bank/issue', body),
  spc: (dcPlanItemId: string) =>
    http
      .get<SpcChart>('/mes/exec/spc', {
        params: { dc_plan_item_id: dcPlanItemId },
      })
      .then((r) => r.data),
  ncrCreate: (body: {
    lot_id: string
    title: string
    severity: string
    defect_code_id?: string | null
    description?: string
    hold?: boolean
  }) => post<NcrDetail>('/mes/exec/ncr', body),
  ncrDetail: (id: string) =>
    http.get<NcrDetail>(`/mes/exec/ncr/${id}`).then((r) => r.data),
  ncrPropose: (
    id: string,
    body: { disposition: string; comment?: string; scrap_reason_id?: string }
  ) => post<NcrDetail>(`/mes/exec/ncr/${id}/propose`, body),
  ncrApprove: (
    id: string,
    body: { decision: 'approve' | 'reject'; comment?: string }
  ) => post<NcrDetail>(`/mes/exec/ncr/${id}/approve`, body),
  ncrCancel: (id: string, comment?: string) =>
    post<NcrDetail>(`/mes/exec/ncr/${id}/cancel`, { comment }),
}

/**
 * 解析晶圆图 CSV：每行 `晶圆编号,x,y,bin`（可有表头），按晶圆分组。
 *
 * @param text - CSV 文本
 * @returns 每片晶圆的芯片列表；格式错误的行号在 `bad` 中
 */
export function parseDieCsv(text: string): {
  maps: { unit_code: string; dies: Die[] }[]
  bad: number[]
} {
  const by = new Map<string, Die[]>()
  const bad: number[] = []
  text.split(/\r?\n/).forEach((line, i) => {
    const s = line.trim()
    if (!s) return
    const [code, x, y, bin] = s.split(/[,\t;]/).map((v) => v.trim())
    if (!/^-?\d+$/.test(x ?? '') || !/^-?\d+$/.test(y ?? '') || !bin) {
      if (i > 0) bad.push(i + 1)
      return
    }
    const list = by.get(code) ?? []
    list.push([Number(x), Number(y), bin])
    by.set(code, list)
  })
  return {
    maps: [...by].map(([unit_code, dies]) => ({ unit_code, dies })),
    bad,
  }
}
