/**
 * BOM 接口（P1 / F3，bom.md v1.1）。
 *
 * - 主表走通用接口 `/mes/bom`（`mes.bom:read` / `mes.bom:write`）；替代料只能挂在物料行上，
 *   同一行内优先级、物料各自唯一。
 * - `GET /mes/bom/tree?bom_id=`：某版本的明细（含替代料）；半成品行带 `child`，
 *   为该半成品当前生效版本的明细（只读，§7.1 两级）
 * - 草稿明细整单替换：`PUT /mes/bom/{id}/lines`（§7.2 / 验收 13，后端 99cc18b），
 *   页面只用它保存明细与替代料，见 `features/mes/product/bom-save.ts`。
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
  /** 替代料（按优先级升序；仅物料行） */
  substitutes?: BomSubstitute[]
  /** 半成品行：该产品当前生效版本（无生效版本时 bom 为 null） */
  child?: BomNode | null
}

export interface BomSubstitute {
  id: string
  bom_line_id: string
  material_id: string
  material_label: string | null
  priority: number
}

/** 树节点；半成品没有生效版本时 `bom` 为 null、`lines` 为空。 */
export interface BomNode {
  bom: Bom | null
  level?: number
  lines: BomLine[]
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

export interface BomSubstituteBody {
  material_id: string | null
  priority: number
}

/** 整单替换的一行：明细字段 + 替代料。 */
export interface BomReplaceLine {
  line_no: number
  component_type: 'material' | 'product'
  material_id?: string | null
  component_product_id?: string | null
  qty: string
  uom_id?: string
  per_basis: string
  scrap_rate: string
  consume_mode: string
  substitutes: BomSubstituteBody[]
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
  /**
   * 整单替换草稿明细（含替代料），后端一个事务完成，失败整单回滚。
   * 错误顺序：403 无权限 → 422 请求体 → 404 → 409 非草稿；业务 422 只报第一条出错行。
   */
  replaceLines: (bomId: string, lines: BomReplaceLine[]) =>
    http.put<BomTree>(`/mes/bom/${bomId}/lines`, { lines }).then((r) => r.data),
  conversions: () =>
    http
      .get<Paged<UomConversion>>('/mes/uom-conversion', {
        params: { page_size: 200 },
      })
      .then((r) => r.data.data),
}
