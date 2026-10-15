/**
 * 草稿明细保存（F3，bom.md §7.2，验收 13）。
 *
 * `PUT /mes/bom/{id}/lines` 整单提交（含替代料），后端一个事务完成：任一处失败整单回滚，
 * 什么都不改，所以失败后页面保留输入、改完直接重试即可。
 * - 物料字段 `material_id`，半成品字段 `component_product_id`，只带当前组件类型那一个。
 * - 每行必须带 `line_no`（后端不自动编号）；编辑框留空的行按顺序接在最大行号后面（+10）。
 * - 请求体严格校验，多出字段 422 `extra_forbidden`，只发白名单字段。
 * - `{lines: []}` 清空明细（删光所有行时就是这样）。
 * - 422 的 loc 是 `["body","lines",k,...]`，k 为请求里的下标，`BomSaveError.lineMap[k]` 换回编辑框下标。
 */
import { t } from '@/i18n'
import {
  bomApi,
  type Bom,
  type BomLine,
  type BomReplaceLine,
  type BomSubstituteBody,
} from '@/lib/api/mes/bom'
import { decimalGreater, decimalText, parseDecimal } from '@/lib/decimal'
import type { BomFieldError } from './bom-errors'

/** D49：用量最多 6 位小数，损耗率最多 4 位小数且在 0 到 1 之间。 */
export const QTY_DECIMALS = 6
export const SCRAP_DECIMALS = 4

/** 编辑中的一条替代料。 */
export interface SubDraft {
  key: string
  id?: string
  material_id: string | null
  material_label: string | null
  priority: string
}

/** 编辑中的一行明细。 */
export interface LineDraft {
  key: string
  id?: string
  line_no: string
  component_type: 'material' | 'product'
  material_id: string | null
  material_label: string | null
  component_product_id: string | null
  component_product_label: string | null
  qty: string
  uom_id: string
  per_basis: string
  scrap_rate: string
  consume_mode: string
  removed?: boolean
  subs: SubDraft[]
}

/**
 * 保存失败：`lineMap[k]` 把请求里第 k 行换回编辑框下标；主表说明保存失败时为 null。
 */
export class BomSaveError {
  constructor(
    readonly error: unknown,
    readonly lineMap: number[] | null = null,
    /** 前端校验没过（没发请求）：字段错误，`line` 为编辑框下标 */
    readonly local: BomFieldError[] | null = null
  ) {}
}

/** 校验一个数值输入，返回错误提示或 null；空值交给后端报必填。 */
function checkNumber(
  v: string,
  max: number,
  range: 'positive' | 'rate'
): string | null {
  if (!v.trim()) return null
  const d = parseDecimal(v)
  if (!d) return t('mes.bomTab.err.notNumber')
  if (range === 'positive' && (d.negative || d.text === '0'))
    return t('mes.bomTab.err.positive')
  if (range === 'rate' && (d.negative || decimalGreater(d.text, '1')))
    return t('mes.bomTab.err.scrapRange')
  if (d.decimals > max) return t('mes.bomTab.err.tooManyDecimals', { n: max })
  return null
}

/** D49 前端校验：返回字段错误（`line` 为编辑框下标），删除的行不查。 */
export function validateRows(rows: LineDraft[]): BomFieldError[] {
  const out: BomFieldError[] = []
  rows.forEach((r, i) => {
    if (r.removed) return
    const q = checkNumber(r.qty, QTY_DECIMALS, 'positive')
    if (q) out.push({ line: i, field: 'qty', message: q })
    const s = checkNumber(r.scrap_rate, SCRAP_DECIMALS, 'rate')
    if (s) out.push({ line: i, field: 'scrap_rate', message: s })
  })
  return out
}

/** 提交用：去掉末尾零的规范字符串（"1.5000000" → "1.5"）。 */
const norm = (v: string) => parseDecimal(v)?.text ?? v.trim()

export const toSubDraft = (s: {
  id: string
  material_id: string
  material_label: string | null
  priority: number
}): SubDraft => ({
  key: s.id,
  id: s.id,
  material_id: s.material_id,
  material_label: s.material_label,
  priority: String(s.priority),
})

export const toLineDraft = (l: BomLine): LineDraft => ({
  key: l.id,
  id: l.id,
  line_no: String(l.line_no),
  component_type: l.component_type,
  material_id: l.material_id,
  material_label: l.material_label,
  component_product_id: l.component_product_id,
  component_product_label: l.component_product_label,
  qty: decimalText(l.qty),
  uom_id: l.uom_id,
  per_basis: l.per_basis,
  scrap_rate: l.scrap_rate == null ? '0' : decimalText(l.scrap_rate),
  consume_mode: l.consume_mode,
  subs: (l.substitutes ?? []).map(toSubDraft),
})

/** 整单的一行：只带白名单字段和当前组件类型对应的引用字段。 */
export function replaceLine(d: LineDraft, lineNo: number): BomReplaceLine {
  const product = d.component_type === 'product'
  return {
    line_no: lineNo,
    component_type: d.component_type,
    ...(product
      ? { component_product_id: d.component_product_id }
      : { material_id: d.material_id }),
    qty: norm(d.qty),
    ...(d.uom_id ? { uom_id: d.uom_id } : {}),
    per_basis: d.per_basis,
    scrap_rate: d.scrap_rate.trim() ? norm(d.scrap_rate) : '0',
    consume_mode: d.consume_mode,
    substitutes: product ? [] : d.subs.map(subBody),
  }
}

export const subBody = (s: SubDraft): BomSubstituteBody => ({
  material_id: s.material_id,
  priority: Number(s.priority),
})

/** 行号：编辑框里填了正整数就用它，留空 / 非法的按顺序接在最大行号后面（+10）。 */
function lineNos(rows: LineDraft[]): number[] {
  const valid = (v: string) => /^\d+$/.test(v.trim()) && Number(v) > 0
  let next = Math.max(
    0,
    ...rows.filter((r) => valid(r.line_no)).map((r) => Number(r.line_no))
  )
  return rows.map((r) => (valid(r.line_no) ? Number(r.line_no) : (next += 10)))
}

export interface SaveArgs {
  bom: Bom
  desc: string
  rows: LineDraft[]
}

/** 保存草稿（主表说明 + 整单明细与替代料）。失败时抛 `BomSaveError`。 */
export async function saveDraft({ bom, desc, rows }: SaveArgs): Promise<void> {
  const local = validateRows(rows)
  if (local.length) throw new BomSaveError(null, null, local)
  if (desc !== (bom.description ?? '')) {
    try {
      await bomApi.update(bom.id, desc.trim())
    } catch (e) {
      throw new BomSaveError(e, null)
    }
  }
  const live = rows.map((r, i) => ({ r, i })).filter((x) => !x.r.removed)
  const nos = lineNos(live.map((x) => x.r))
  const lines = live.map((x, k) => replaceLine(x.r, nos[k]))
  try {
    await bomApi.replaceLines(bom.id, lines)
  } catch (e) {
    throw new BomSaveError(
      e,
      live.map((x) => x.i)
    )
  }
}
