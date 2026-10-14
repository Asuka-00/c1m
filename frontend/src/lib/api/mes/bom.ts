/**
 * BOM 接口（P1 / F3，bom.md v1.1）。
 *
 * - 主表 / 明细走通用接口：`/mes/bom`、`/mes/bom-line`（`mes.bom:read` / `mes.bom:write`）
 * - `GET /mes/bom/tree?bom_id=`：某版本的明细（含替代料）
 * - `POST /mes/bom/{id}/activate`、`/void`（`mes.bom:activate`）、`/copy`（`mes.bom:write`）：
 *   请求体必须为空（D32，带任何字段 422），这里不传 data。
 * - `GET /mes/uom-conversion`：单位换算，明细单位只能从中选择。
 *
 * 时间字段为带 Z 的 UTC，显示时用 `fmtDateTime`；数量是后端 Decimal(18,6)，原样显示不四舍五入。
 */
import { http } from '../client'
import type { Paged } from '../types'

export type BomStatus = 'draft' | 'active' | 'superseded' | 'void'

export interface Bom {
  id: string
  product_id: string
  version: number
  status: BomStatus
  effective_at: string | null
  confirmed_by: string | null
  confirmed_at: string | null
  copied_from_id: string | null
  copied_from_label: string | null
  description: string | null
  created_at: string
  updated_at: string
}

export interface BomLine {
  id: string
  bom_id: string
  line_no: number
  component_type: 'material' | 'product'
  material_id: string | null
  material_label: string | null
  component_product_id: string | null
  component_product_label: string | null
  qty: number | string
  uom_id: string
  uom_label: string | null
  per_basis: string
  scrap_rate: number | null
  consume_mode: string
  remark: string | null
}

export interface BomTree {
  bom: Bom
  level: number
  lines: BomLine[]
}

export interface UomConversion {
  id: string
  from_uom_id: string
  to_uom_id: string
  from_uom_label: string | null
  to_uom_label: string | null
  factor: number
}

/** 新建 / 修改明细的请求体（数量以字符串传，避免浮点误差）。 */
export interface BomLineBody {
  line_no?: number
  component_type?: 'material'
  material_id?: string
  qty?: string
  uom_id?: string
  per_basis?: string
  scrap_rate?: number
  consume_mode?: string
  remark?: string | null
}

export const bomApi = {
  list: (productId: string) =>
    http
      .get<Paged<Bom>>('/mes/bom', {
        params: { product: productId, sort_by: 'version', page_size: 100 },
      })
      .then((r) => r.data.data),
  tree: (bomId: string) =>
    http
      .get<BomTree>('/mes/bom/tree', { params: { bom_id: bomId } })
      .then((r) => r.data),
  create: (productId: string, description: string) =>
    http
      .post<Bom>('/mes/bom', {
        product_id: productId,
        description: description || null,
      })
      .then((r) => r.data),
  update: (id: string, description: string) =>
    http
      .patch<Bom>(`/mes/bom/${id}`, { description: description || null })
      .then((r) => r.data),
  /** 生效：请求体为空（D32）。 */
  activate: (id: string) =>
    http.post<Bom>(`/mes/bom/${id}/activate`).then((r) => r.data),
  /** 作废：请求体为空（D32）。 */
  void: (id: string) =>
    http.post<Bom>(`/mes/bom/${id}/void`).then((r) => r.data),
  /** 复制为新草稿：请求体为空（D32）。 */
  copy: (id: string) =>
    http.post<Bom>(`/mes/bom/${id}/copy`).then((r) => r.data),
  addLine: (bomId: string, body: BomLineBody) =>
    http
      .post<BomLine>('/mes/bom-line', { bom_id: bomId, ...body })
      .then((r) => r.data),
  updateLine: (id: string, body: BomLineBody) =>
    http.patch<BomLine>(`/mes/bom-line/${id}`, body).then((r) => r.data),
  removeLine: (id: string) =>
    http.delete(`/mes/bom-line/${id}`).then((r) => r.data),
  conversions: () =>
    http
      .get<Paged<UomConversion>>('/mes/uom-conversion', {
        params: { page_size: 200 },
      })
      .then((r) => r.data.data),
}
