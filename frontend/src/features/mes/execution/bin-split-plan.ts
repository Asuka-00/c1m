/**
 * 按 bin 拆批（B8 / F7）的纯函数：草稿 → 请求体、bin 分档汇总、守恒与错误文案。
 *
 * 后端规则（execution/bin_split.py）：
 * - 有坐标图的晶圆：各 bin 数量取自图，不能人工录入；排除类 bin（按定义集 bin_type）不进子批；
 *   子批合计 + 排除 = 坐标图总数，否则 422 map_qty_mismatch。
 * - 没有坐标图：必须人工录入各 bin 数量并选原因码；合计须等于产品 gross die，
 *   否则 422 bin_split_qty_mismatch（带期望数和实际数）。
 * - 默认每个 bin 一个子批，子批带 bin_code。
 */
import { AxiosError } from 'axios'
import { t } from '@/i18n'
import type { BinSplitBody, BinSplitPreview } from '@/lib/api/mes/execution'
import { intOf, transformErrorText, type TrfWafer } from './transform-plan'

export interface BinRow {
  bin: string
  qty: string
}

export interface BinDraft {
  /** 没有坐标图的晶圆：人工录入的 bin 行 */
  manual: Record<string, BinRow[]>
  reason_id: string | null
  reason_label: string | null
  comment: string
}

export const emptyBinDraft = (): BinDraft => ({
  manual: {},
  reason_id: null,
  reason_label: null,
  comment: '',
})

/** bin 码排序：数字在前按数值，其他按字母（与后端 `_bin_key` 一致）。 */
export function sortBins(codes: Iterable<string>): string[] {
  return [...new Set(codes)].sort((a, b) => {
    const na = /^\d+$/.test(a)
    const nb = /^\d+$/.test(b)
    if (na && nb) return Number(a) - Number(b)
    if (na !== nb) return na ? -1 : 1
    return a < b ? -1 : a > b ? 1 : 0
  })
}

const filled = (rows: BinRow[] | undefined) =>
  (rows ?? []).filter((r) => r.bin.trim() || r.qty.trim())

/** 人工 bin 行合计（非法行按 0）。 */
export const manualSum = (rows: BinRow[] | undefined) =>
  filled(rows).reduce((n, r) => {
    const q = intOf(r.qty)
    return n + (q && !Number.isNaN(q) ? q : 0)
  }, 0)

/** 本地校验：返回本地化提示列表（空 = 可预览）。 */
export function binDraftErrors(wafers: TrfWafer[], d: BinDraft): string[] {
  const out: string[] = []
  if (!wafers.length) out.push(t('mes.trf.e.noWafer'))
  let manual = false
  for (const w of wafers) {
    if (w.map !== null) continue
    const rows = filled(d.manual[w.id])
    if (!rows.length) {
      out.push(t('mes.bin.e.need', { wafer: w.code }))
      continue
    }
    manual = true
    const seen = new Set<string>()
    for (const r of rows) {
      const code = r.bin.trim()
      const q = intOf(r.qty)
      if (!code || code.length > 32)
        out.push(t('mes.bin.e.code', { wafer: w.code }))
      if (q === null || Number.isNaN(q))
        out.push(t('mes.trf.e.int', { wafer: w.code }))
      if (code && seen.has(code))
        out.push(t('mes.bin.e.dup', { wafer: w.code, bin: code }))
      seen.add(code)
    }
  }
  if (manual && !d.reason_id) out.push(t('mes.bin.e.reason'))
  return [...new Set(out)]
}

/** 草稿 → 请求体（不带 outputs：每个 bin 一个子批）。 */
export function binSplitBody(
  lotId: string,
  wafers: TrfWafer[],
  d: BinDraft
): BinSplitBody {
  const manual = wafers
    .filter((w) => w.map === null && filled(d.manual[w.id]).length)
    .map((w) => ({
      wafer_id: w.id,
      bins: filled(d.manual[w.id]).map((r) => ({
        bin_code: r.bin.trim(),
        qty: intOf(r.qty) ?? 0,
      })),
    }))
  return {
    input_lot_ids: [lotId],
    ...(manual.length ? { manual_bins: manual } : {}),
    ...(d.reason_id ? { reason_id: d.reason_id } : {}),
    ...(d.comment.trim() ? { comment: d.comment.trim() } : {}),
  }
}

/** 预览 → bin 分档汇总：每个 bin 各片数量、合计、是否排除；每片守恒与差额。 */
export function binSummary(p: BinSplitPreview) {
  const bins = sortBins(p.inputs.flatMap((x) => Object.keys(x.bin_counts)))
  const rows = bins.map((bin) => {
    const per = p.inputs.map((x) => x.bin_counts[bin] ?? 0)
    const split = p.inputs.reduce((n, x) => n + (x.split_counts[bin] ?? 0), 0)
    const total = per.reduce((a, b) => a + b, 0)
    return { bin, per, total, excluded: total > 0 && split === 0 }
  })
  const wafers = p.inputs.map((x) => ({
    wafer: x.wafer,
    total: x.total_qty,
    children: x.children_qty,
    excluded: x.excluded_qty,
    diff: x.children_qty + x.excluded_qty - x.total_qty,
    ok: x.conserved && x.children_qty + x.excluded_qty === x.total_qty,
  }))
  return { bins: rows, wafers, ok: wafers.every((w) => w.ok) }
}

const signed = (n: number) => (n > 0 ? `+${n}` : String(n))

/** 按 bin 拆批错误 → 本地化文本（守恒错误带期望数、实际数和差额）。 */
export function binSplitErrorText(e: unknown): string {
  if (e instanceof AxiosError && e.response?.status === 422) {
    const d = (e.response.data as { detail?: unknown })?.detail
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const x = d as Record<string, unknown>
      const n = (k: string) => Number(x[k] ?? 0)
      if (x.code === 'map_qty_mismatch')
        return t('mes.bin.be.mapQty', {
          children: n('children_qty'),
          excluded: n('excluded_qty'),
          total: n('total_qty'),
          diff: signed(n('children_qty') + n('excluded_qty') - n('total_qty')),
        })
      if (x.code === 'bin_split_qty_mismatch')
        return t('mes.bin.be.binQty', {
          wafer: x.wafer ?? '',
          actual: n('bins_qty'),
          expected: n('expected_qty'),
          diff: signed(n('bins_qty') - n('expected_qty')),
        })
      if (x.code === 'bin_split_unassigned')
        return t('mes.bin.be.unassigned', {
          list: ((x.bin_codes as string[]) ?? []).join(', '),
        })
    }
  }
  return transformErrorText(e)
}
