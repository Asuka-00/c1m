/**
 * 前端对后端表单元数据的临时覆盖（集中在此，便于整体移除）。
 *
 * TODO(D25/D26)：后端 qtime_rule 表单配置更新后（reason 去掉 required_when 并带帮助文本、
 * qtime_action 枚举去掉 scrap），删除本文件及以下引用：
 *   - required.ts       overrideRequiredWhen
 *   - labels.ts         overrideHelpKey
 *   - entity-form.tsx   overrideEnumOptions
 */
import type { MesEntity, MesField } from '@/lib/api/mes/common'

/** D25：Q-Time 规则原因码可空（留空时后端使用 qtime_expired）。 */
const D25_REASON = 'qtime_rule.reason'

/** 覆盖后的 required_when；无覆盖时返回字段原值（不修改元数据本身）。 */
export function overrideRequiredWhen(
  e: MesEntity,
  f: MesField
): MesField['required_when'] {
  const rw = f.required_when
  if (`${e.code}.${f.name}` !== D25_REASON || !rw?.action) return rw
  const rest = Object.fromEntries(
    Object.entries(rw).filter(([k]) => k !== 'action')
  )
  return Object.keys(rest).length ? rest : null
}

/** 前端补充的字段帮助 i18n 键；无覆盖时返回 null。 */
export const overrideHelpKey = (e: MesEntity, f: MesField) =>
  `${e.code}.${f.name}` === D25_REASON ? 'mes.qtimeRule.reasonHint' : null

/** D26：Q-Time 动作只有 warn / hold / rework；表单下拉中隐藏的枚举值（枚举名 → 值）。列表 / 筛选 / 标签不受影响。 */
const HIDDEN_ENUM: Record<string, readonly string[]> = {
  qtime_action: ['scrap'],
}

/** 表单可选的枚举值；当前值即使已被隐藏也保留，旧数据（如 scrap）可正常显示。 */
export function overrideEnumOptions(
  en: string,
  options: readonly string[],
  current?: string
): string[] {
  const hidden = HIDDEN_ENUM[en]
  if (!hidden) return [...options]
  return options.filter((o) => !hidden.includes(o) || o === current)
}
