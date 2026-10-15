/** Q-Time 自动 Hold 附加字段（D20）的类型与格式化。 */
import { t } from '@/i18n'

/** D20：Q-Time 自动 Hold 记录的可选字段（手动 Hold 与旧记录为 null / 缺失）。 */
export interface QtimeHoldFields {
  qtime_rule_id?: string | null
  qtime_from_step_id?: string | null
  qtime_to_step_id?: string | null
  qtime_overdue_seconds?: number | null
  /** 起止工步显示名（后端只读、可空）；为空时前端用工步列表或 id 兜底 */
  qtime_from_step_name?: string | null
  qtime_to_step_name?: string | null
}

/** 工步 id -> 显示名（如 "10 · ETCH"）；查不到时显示 id。 */
export type StepNames = Record<string, string>

/** 超时秒数格式化为本地化的“X 小时 Y 分”（不足 1 分按 1 分）。 */
export function fmtOverdue(seconds: number) {
  const mins = Math.max(1, Math.ceil(seconds / 60))
  const h = Math.floor(mins / 60)
  const m = mins % 60
  if (!h) return t('mes.qtimeHold.minutes', { m })
  if (!m) return t('mes.qtimeHold.hours', { h })
  return t('mes.qtimeHold.hoursMinutes', { h, m })
}

export const hasQtimeInfo = (x: QtimeHoldFields) =>
  x.qtime_rule_id != null ||
  x.qtime_from_step_id != null ||
  x.qtime_to_step_id != null ||
  !!x.qtime_from_step_name ||
  !!x.qtime_to_step_name ||
  (x.qtime_overdue_seconds != null && x.qtime_overdue_seconds > 0)
