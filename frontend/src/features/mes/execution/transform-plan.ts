/**
 * 单位转换（B5 / F8）的纯函数：草稿 → 请求体、逐片守恒、错误与提示文案。
 *
 * 后端规则（execution/transform.py）：
 * - 有坐标图的晶圆：良品数取自图，不能人工录入；分配数 + 不良 + 排除 = 图总数（422 map_qty_mismatch）。
 * - 没有坐标图：人工录入良品数（必须带原因码）；不录则用产品 gross die（提示 no_map_gross_die）；
 *   分配数 ≠ 良品数 → 422 transform_qty_mismatch。
 * - 输出为条（strip）时必须填条数；其他类型数量 = 分配的 die 数。
 */
import { AxiosError } from 'axios'
import { t } from '@/i18n'
import type {
  TrackUnitKind,
  TransformBody,
  TransformType,
} from '@/lib/api/mes/execution'
import { mesErrorMessage } from '@/features/mes/common/required'

export const TRANSFORM_TYPES: TransformType[] = [
  'dicing',
  'die_attach',
  'singulation',
]
export const TRACK_UNIT_KINDS: TrackUnitKind[] = [
  'die',
  'strip',
  'package',
  'unit',
]

/** 晶圆及其坐标图：map 为 null 表示没有坐标图，undefined 表示查询中或查不到（以预览为准）。 */
export interface TrfWafer {
  id: string
  code: string
  map?: {
    total_qty: number
    good_qty: number
    excluded_qty: number
    map_version: number
  } | null
  /** 产品 gross die（没有坐标图且不人工录入时的良品数；未知为 undefined） */
  gross?: number
}

export interface TrfOutput {
  product_id: string | null
  product_label: string | null
  route_id: string | null
  route_label: string | null
  kind: TrackUnitKind
  qty: string
  /** 晶圆 id → 分给本输出的 die 数（空 = 单输出时默认取良品数） */
  alloc: Record<string, string>
}

export interface TrfDraft {
  type: TransformType
  outputs: TrfOutput[]
  /** 没有坐标图的晶圆：人工良品 / 不良数 */
  manual: Record<string, { good: string; fail: string }>
  reason_id: string | null
  reason_label: string | null
  comment: string
}

export const emptyOutput = (): TrfOutput => ({
  product_id: null,
  product_label: null,
  route_id: null,
  route_label: null,
  kind: 'die',
  qty: '',
  alloc: {},
})

export const emptyDraft = (): TrfDraft => ({
  type: 'dicing',
  outputs: [emptyOutput()],
  manual: {},
  reason_id: null,
  reason_label: null,
  comment: '',
})

const INT = /^\d+$/
/** 非负整数文本 → 数字；空为 null；非法为 NaN。 */
export function intOf(s: string | undefined): number | null {
  const v = (s ?? '').trim()
  if (!v) return null
  return INT.test(v) ? Number(v) : NaN
}

/** 晶圆是否走人工良品数（明确没有坐标图且录入了良品数）。 */
export const isManual = (w: TrfWafer, d: TrfDraft) =>
  w.map === null && intOf(d.manual[w.id]?.good) !== null

/** 晶圆良品数：坐标图 → 图良品数；人工 → 录入值；留空 → 产品 gross die；未知 → null。 */
export function goodOf(w: TrfWafer, d: TrfDraft): number | null {
  if (w.map) return w.map.good_qty
  if (w.map === null) {
    const g = intOf(d.manual[w.id]?.good)
    if (g === null) return w.gross ?? null
    return Number.isNaN(g) ? null : g
  }
  return null
}

/** 某输出从某晶圆分到的 die 数（单输出且未填时默认取良品数）。 */
export function allocOf(o: TrfOutput, w: TrfWafer, d: TrfDraft): number {
  const v = intOf(o.alloc[w.id])
  if (v !== null) return Number.isNaN(v) ? 0 : v
  return d.outputs.length === 1 ? (goodOf(w, d) ?? 0) : 0
}

/** 逐片守恒：良品数已知时给出差值（分配 − 良品），未知为 null。 */
export function balance(wafers: TrfWafer[], d: TrfDraft) {
  return wafers.map((w) => {
    const good = goodOf(w, d)
    const allocated = d.outputs.reduce((n, o) => n + allocOf(o, w, d), 0)
    return {
      id: w.id,
      code: w.code,
      good,
      allocated,
      diff: good === null ? null : allocated - good,
    }
  })
}

/** 提交前的本地校验：返回本地化提示列表（空 = 可预览）。 */
export function draftErrors(wafers: TrfWafer[], d: TrfDraft): string[] {
  const out: string[] = []
  if (!wafers.length) out.push(t('mes.trf.e.noWafer'))
  for (const w of wafers) {
    const m = d.manual[w.id]
    if (w.map === null && m)
      for (const v of [m.good, m.fail])
        if (Number.isNaN(intOf(v)))
          out.push(t('mes.trf.e.int', { wafer: w.code }))
  }
  if (wafers.some((w) => isManual(w, d)) && !d.reason_id)
    out.push(t('mes.trf.e.reason'))
  d.outputs.forEach((o, i) => {
    const n = i + 1
    if (!o.product_id) out.push(t('mes.trf.e.product', { n }))
    if (!o.route_id) out.push(t('mes.trf.e.route', { n }))
    const q = intOf(o.qty)
    if (o.kind === 'strip' && !(q && q > 0))
      out.push(t('mes.trf.e.strip', { n }))
    if (Object.values(o.alloc).some((v) => Number.isNaN(intOf(v))))
      out.push(t('mes.trf.e.alloc', { n }))
    // 良品数未知（如留空且查不到 gross die）时不拦，交给后端预览判定。
    const known = wafers.every((w) => goodOf(w, d) !== null)
    if (known && wafers.reduce((s, w) => s + allocOf(o, w, d), 0) < 1)
      out.push(t('mes.trf.e.noDie', { n }))
  })
  for (const b of balance(wafers, d))
    if (b.diff)
      out.push(
        t('mes.trf.e.balance', {
          wafer: b.code,
          allocated: b.allocated,
          good: b.good,
        })
      )
  return [...new Set(out)]
}

/** 草稿 → 请求体（只带后端认识的字段；0 颗的来源不发送）。 */
export function transformBody(
  lotId: string,
  wafers: TrfWafer[],
  d: TrfDraft
): TransformBody {
  const manual = wafers
    .filter((w) => isManual(w, d))
    .map((w) => ({
      wafer_id: w.id,
      good_qty: intOf(d.manual[w.id].good) ?? 0,
      fail_qty: intOf(d.manual[w.id].fail) || 0,
    }))
  return {
    transform_type: d.type,
    input_lot_ids: [lotId],
    outputs: d.outputs.map((o) => ({
      product_id: o.product_id ?? '',
      route_id: o.route_id ?? '',
      track_unit_kind: o.kind,
      ...(o.kind === 'strip' ? { qty: intOf(o.qty) ?? 0 } : {}),
      sources: wafers
        .map((w) => ({ wafer_id: w.id, qty: allocOf(o, w, d) }))
        .filter((s) => s.qty > 0),
    })),
    ...(manual.length ? { manual_good: manual } : {}),
    ...(d.reason_id ? { reason_id: d.reason_id } : {}),
    ...(d.comment.trim() ? { comment: d.comment.trim() } : {}),
  }
}

/** 预览 / 提交返回的提示（no_map_gross_die 等）。 */
export function trfWarningText(w: {
  code: string
  message?: string
  wafer?: string
}) {
  if (w.code === 'no_map_gross_die')
    return t('mes.trf.warn.gross', { wafer: w.wafer ?? '' })
  return w.message ?? w.code
}

const MSG_RULES: [RegExp, string][] = [
  [/manual good qty not allowed/, 'mes.trf.be.manualWithMap'],
  [/manual bins not allowed/, 'mes.bin.be.manualWithMap'],
  [/enter bin quantities with a reason/, 'mes.bin.be.needManual'],
  [/reason required for manual bin/, 'mes.bin.be.reason'],
  [/duplicate bin/, 'mes.bin.be.duplicate'],
  [/no gross die to check bins/, 'mes.bin.be.noGross'],
  [/different steps; route required/, 'mes.bin.be.route'],
  [/no substrate map and product has no gross die/, 'mes.trf.be.noGross'],
  [/reason required/, 'mes.trf.be.reason'],
  [/reason not found/, 'mes.trf.be.reasonNotFound'],
  [/no wafer units/, 'mes.trf.be.noWafer'],
  [/strip count required/, 'mes.trf.be.strip'],
  [/at least one die/, 'mes.trf.be.noDie'],
  [/product not found/, 'mes.trf.be.product'],
  [/route not found/, 'mes.trf.be.route'],
  [/not an input wafer/, 'mes.trf.be.notInput'],
]

/** 单位转换 / 拆批错误 → 本地化文本（守恒错误带期望数和实际数）。 */
export function transformErrorText(e: unknown): string {
  if (e instanceof AxiosError && e.response?.status === 422) {
    const d = (e.response.data as { detail?: unknown })?.detail
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const x = d as Record<string, unknown>
      if (x.code === 'map_qty_mismatch')
        return t('mes.trf.be.mapQty', {
          children: x.children_qty,
          excluded: x.excluded_qty,
          total: x.total_qty,
        })
      if (x.code === 'transform_qty_mismatch')
        return t('mes.trf.be.trfQty', {
          wafer: x.wafer ?? '',
          allocated: x.allocated_qty,
          good: x.good_qty,
        })
    }
    if (Array.isArray(d)) {
      const msgs = (d as { msg?: string; type?: string }[]).map((it) => {
        const msg = String(it.msg ?? '')
        if (it.type === 'extra_forbidden') return t('mes.trf.be.extra')
        const hit = MSG_RULES.find(([re]) => re.test(msg))
        const wafer = /^([^:]+):/.exec(msg)?.[1]
        if (!hit) return msg
        return wafer ? `${wafer}: ${t(hit[1])}` : t(hit[1])
      })
      return [...new Set(msgs)].join('；')
    }
  }
  return mesErrorMessage(e, undefined)
}
