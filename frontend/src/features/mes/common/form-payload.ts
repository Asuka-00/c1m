/** 实体表单提交体（从 entity-form 拆出，便于测试）。 */
import type { MesEntity } from '@/lib/api/mes/common'
import { parseDecimal } from '@/lib/decimal'
import { decimalLimit, requiredBy } from './required'

type V = Record<string, unknown>

/** 无论元数据是否标 system，都不提交的只读字段（实体.字段）。 */
export const NEVER_SUBMIT = new Set(['alarm_code.migration_note'])

/** 表单值 → 提交体：跳过系统 / 只读字段，按类型转换。 */
export function toPayload(e: MesEntity, v: V, hidden: Set<string>): V {
  const out: V = {}
  for (const f of e.fields) {
    if (f.system || NEVER_SUBMIT.has(`${e.code}.${f.name}`)) continue
    if (hidden.has(f.column) && v[f.column] === '') continue
    // 条件字段未满足条件时清空（如切换卡控绑定范围后残留的旧范围值）
    if (f.only_when_required && !requiredBy(e, f, v)) {
      out[f.column] = null
      continue
    }
    const x = v[f.column]
    if (f.type === 'json') {
      out[f.column] = x === '' ? null : JSON.parse(String(x))
    } else if (f.type === 'float' && decimalLimit(f) != null) {
      // D72：定点字段按十进制字符串提交（不经过浮点，不丢精度）
      out[f.column] =
        x === '' || x == null
          ? null
          : (parseDecimal(String(x))?.text ?? String(x).trim())
    } else if (f.type === 'int' || f.type === 'float') {
      out[f.column] = x === '' || x == null ? null : Number(x)
    } else if (f.type === 'bool') {
      out[f.column] = !!x
    } else {
      out[f.column] = x === '' ? null : x
    }
  }
  for (const f of e.fields)
    if (f.default_from && out[f.column] == null && v[f.default_from])
      out[f.column] = v[f.default_from]
  out.attrs = v.attrs
  return out
}
