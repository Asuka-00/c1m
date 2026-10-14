/**
 * Q-Time 预警履历（Q-01，`lot_history.action = qtime_warned`）的说明文本。
 *
 * 决策 Q-01：warn 超时写一条批次履历，带规则、工步、超时秒数。后端尚未实现（截至 be/p2 未出现该事件），
 * 字段名按决策描述取：规则 `rule` / `qtime_rule_code`，工步 `step_seq` / `step`，
 * 超时秒数 `overdue_seconds`（兼容 `over_seconds`）。后端落地后按实际字段核对。
 */
import { t } from '@/i18n'

/** 秒数 → 「1 小时 2 分」/「45 秒」（三语）。 */
export function durationText(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h) return t('mes.qtw.hm', { h, m })
  if (m) return t('mes.qtw.m', { m })
  return t('mes.qtw.s', { s })
}

export function qtimeWarnedText(d: Record<string, unknown>): string {
  const rule = d.rule ?? d.qtime_rule_code ?? d.qtime_rule ?? ''
  const step = d.step_seq ?? d.step ?? ''
  const sec = Number(d.overdue_seconds ?? d.over_seconds ?? 0)
  return t('mes.qtw.text', {
    rule: String(rule) || '—',
    step: String(step) || '—',
    over: durationText(sec),
  })
}
