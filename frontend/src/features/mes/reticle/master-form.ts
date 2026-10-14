/** 光罩主数据表单逻辑（P3-F3）。 */
import { t } from '@/i18n'
import {
  RETICLE_MASTER_FIELDS,
  type Reticle,
  type ReticleMasterInput,
} from '@/lib/api/mes/reticle'
import { compareDecimal, decimalText, parseDecimal } from '@/lib/decimal'

export type F = (typeof RETICLE_MASTER_FIELDS)[number]
export type V = Record<F, string>

export const init = (r: Reticle | null): V =>
  Object.fromEntries(
    RETICLE_MASTER_FIELDS.map((k) => [
      k,
      r?.[k] == null ? (k === 'count_basis' ? 'track_out' : '') : String(r[k]),
    ])
  ) as V

/** 表单校验（前端先拦，后端仍以 422 为准）：code 必填；max_shots 正整数；warn_ratio ∈ (0, 1]，最多 4 位小数。 */
export function masterErrors(v: V): Partial<Record<F, string>> {
  const e: Partial<Record<F, string>> = {}
  if (!v.code.trim()) e.code = t('mes.reticle.master.errRequired')
  const ms = v.max_shots.trim()
  if (ms && (!/^\d+$/.test(ms) || compareDecimal(ms, 0) !== 1))
    e.max_shots = t('mes.reticle.master.errMaxShots')
  const wr = v.warn_ratio.trim()
  if (
    wr &&
    (parseDecimal(wr) == null ||
      !/^\d*(\.\d{1,4})?$/.test(wr) ||
      compareDecimal(wr, 0) !== 1 ||
      compareDecimal(wr, 1) === 1)
  )
    e.warn_ratio = t('mes.reticle.master.errWarnRatio')
  return e
}

/** 请求体：空串 → null；数值 D76 定点字符串（规范化，不经浮点）；编辑只发改动字段。 */
export function masterBody(v: V, r: Reticle | null): ReticleMasterInput {
  const out: Record<string, string | null> = {}
  for (const k of RETICLE_MASTER_FIELDS) {
    const raw = v[k].trim()
    let val: string | null = raw === '' ? null : raw
    if (val != null && (k === 'max_shots' || k === 'warn_ratio'))
      val = decimalText(val)
    const old = r?.[k] == null ? null : String(r[k])
    const same =
      old === val ||
      (old != null &&
        val != null &&
        (k === 'max_shots' || k === 'warn_ratio') &&
        compareDecimal(old, val) === 0)
    if (!r || !same) out[k] = val
  }
  if (!r) for (const k of Object.keys(out)) if (out[k] == null) delete out[k]
  return out as ReticleMasterInput
}
