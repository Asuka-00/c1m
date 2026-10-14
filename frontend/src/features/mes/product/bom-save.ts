/**
 * 草稿明细保存（F3，bom.md §7.2，验收 13）。
 *
 * 两种实现，页面只调用 `saveDraft`：
 * - `replace`：`PUT /mes/bom/{id}/lines` 整单提交（含替代料），后端一个事务完成，失败时整单不生效。
 * - `perLine`：逐行调用通用接口（明细 / 替代料），中途失败时已提交的部分不回滚。
 *
 * 后端目前没有整单替换接口，`BOM_REPLACE_LINES` 先为 false；接口上线后改成 true 即可切换，
 * 页面与错误定位（`BomSaveError.line` 为编辑框里的行下标）不用改。
 */
import {
  bomApi,
  type Bom,
  type BomLine,
  type BomLineBody,
  type BomReplaceLine,
  type BomSubstituteBody,
} from '@/lib/api/mes/bom'

/** 后端提供 `PUT /mes/bom/{id}/lines` 后置为 true。 */
export const BOM_REPLACE_LINES = false

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
 * 保存失败：`line` 为编辑框行下标（主表字段为 null），`sub` 为该行替代料下标。
 * 整单模式下 `lineMap[k]` 把请求里第 k 行换回编辑框下标（422 的 loc 为 ["body","lines",k,...]）。
 */
export class BomSaveError {
  constructor(
    readonly error: unknown,
    readonly line: number | null,
    readonly sub: number | null = null,
    readonly lineMap: number[] | null = null
  ) {}
}

const qtyText = (q: number | string | null | undefined) =>
  q == null ? '' : String(q)

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
  qty: qtyText(l.qty),
  uom_id: l.uom_id,
  per_basis: l.per_basis,
  scrap_rate: l.scrap_rate == null ? '0' : String(l.scrap_rate),
  consume_mode: l.consume_mode,
  subs: (l.substitutes ?? []).map(toSubDraft),
})

/** 明细请求体：只带当前组件类型对应的引用字段（另一个由后端清空）。 */
export function lineBody(d: LineDraft): BomLineBody {
  const product = d.component_type === 'product'
  return {
    line_no: Number(d.line_no),
    component_type: d.component_type,
    ...(product
      ? { component_product_id: d.component_product_id ?? undefined }
      : { material_id: d.material_id ?? undefined }),
    qty: d.qty.trim(),
    uom_id: d.uom_id || undefined,
    per_basis: d.per_basis,
    scrap_rate: Number(d.scrap_rate || 0),
    consume_mode: d.consume_mode,
  }
}

export const subBody = (s: SubDraft): BomSubstituteBody => ({
  material_id: s.material_id,
  priority: Number(s.priority),
})

/** 只传改过的字段。 */
export function diff(a: BomLineBody, b: BomLineBody): BomLineBody {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(b))
    if (a[k as keyof BomLineBody] !== v) out[k] = v
  return out as BomLineBody
}

/** 替代料只对物料行有效。 */
const liveSubs = (d: LineDraft) =>
  d.component_type === 'material' ? d.subs : []

export interface SaveArgs {
  bom: Bom
  desc: string
  rows: LineDraft[]
  /** 已保存状态（按明细 id）；逐行模式下每步成功后就地更新，重试不会重复提交 */
  saved: Map<string, LineDraft>
  /** 逐行模式：某行 / 替代料拿到新 id 时回写到编辑框 */
  patchRow: (i: number, patch: Partial<LineDraft>) => void
}

/** 保存草稿（主表说明 + 明细 + 替代料）。失败时抛 `BomSaveError`。 */
export async function saveDraft(
  a: SaveArgs,
  mode: 'replace' | 'perLine' = BOM_REPLACE_LINES ? 'replace' : 'perLine'
): Promise<void> {
  if (a.desc !== (a.bom.description ?? '')) {
    try {
      await bomApi.update(a.bom.id, a.desc.trim())
    } catch (e) {
      throw new BomSaveError(e, null)
    }
  }
  if (mode === 'replace') return saveReplace(a)
  return savePerLine(a)
}

async function saveReplace({ bom, rows }: SaveArgs) {
  const idx: number[] = []
  const lines: BomReplaceLine[] = []
  rows.forEach((r, i) => {
    if (r.removed) return
    idx.push(i)
    lines.push({ ...lineBody(r), substitutes: liveSubs(r).map(subBody) })
  })
  try {
    await bomApi.replaceLines(bom.id, lines)
  } catch (e) {
    throw new BomSaveError(e, null, null, idx)
  }
}

const sameSub = (a: SubDraft, b: SubDraft) =>
  a.material_id === b.material_id && Number(a.priority) === Number(b.priority)

async function savePerLine({ bom, rows, saved, patchRow }: SaveArgs) {
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]
    const old = r.id ? saved.get(r.id) : undefined
    let id = r.id
    const subs = liveSubs(r).map((s) => ({ ...s }))
    try {
      if (r.removed) {
        // 删除明细时后端级联删除其替代料
        if (r.id) {
          await bomApi.removeLine(r.id)
          saved.delete(r.id)
        }
        continue
      }
      // 1) 先删掉去掉的 / 改过的替代料（同一行内优先级唯一，先删后建才能互换优先级）
      if (old) {
        for (const s of [...old.subs]) {
          const now = subs.find((x) => x.id === s.id)
          if (now && sameSub(now, s)) continue
          await bomApi.removeSubstitute(s.id!)
          old.subs = old.subs.filter((x) => x !== s)
          if (now) now.id = undefined
        }
      }
      // 2) 明细本身
      if (!id) {
        id = (await bomApi.addLine(bom.id, lineBody(r))).id
        saved.set(id, { ...r, id, subs: [] })
        patchRow(i, { id, subs: subs.map((x) => ({ ...x })) })
      } else if (old) {
        const ch = diff(lineBody(old), lineBody(r))
        if (Object.keys(ch).length) await bomApi.updateLine(id, ch)
        saved.set(id, { ...r, subs: old.subs })
        patchRow(i, { subs: subs.map((x) => ({ ...x })) })
      }
    } catch (e) {
      throw new BomSaveError(e, i)
    }
    // 3) 新建替代料（新加的，或改过、上一步已删掉的）
    const target = saved.get(id!)!
    for (let j = 0; j < subs.length; j++) {
      if (subs[j].id) continue
      try {
        const created = await bomApi.addSubstitute(id!, subBody(subs[j]))
        subs[j] = { ...subs[j], id: created.id }
        target.subs = [...target.subs, subs[j]]
        patchRow(i, { subs: subs.map((x) => ({ ...x })) })
      } catch (e) {
        throw new BomSaveError(e, i, j)
      }
    }
  }
}
