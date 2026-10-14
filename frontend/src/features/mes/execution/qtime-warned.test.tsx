import i18n from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { HistoryTimeline } from './lot-trace'
import { durationText, qtimeWarnedText } from './qtime-warned'

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('Q-Time 预警履历 qtime_warned（Q-01）', () => {
  it('规则、工步、超时时长三语文案', async () => {
    const d = { rule: 'QT-ETCH', step_seq: 30, overdue_seconds: 3720 }
    expect(qtimeWarnedText(d)).toBe(
      'Q-Time 预警：规则 QT-ETCH · 工步 30 · 已超出预警 1 小时 2 分'
    )
    expect(durationText(45)).toBe('45 秒')
    await i18n.changeLanguage('en')
    expect(qtimeWarnedText(d)).toBe(
      'Q-Time warning: rule QT-ETCH · step 30 · 1 h 2 min past the warning limit'
    )
    await i18n.changeLanguage('ja')
    expect(
      qtimeWarnedText({ qtime_rule_code: 'QT-1', over_seconds: 120 })
    ).toBe('Q-Time 警告：ルール QT-1 · 工程 — · 警告値を 2 分 超過')
  })

  it('批次履历显示动作名和说明', async () => {
    const s = await render(
      <HistoryTimeline
        rows={[
          {
            id: 'h1',
            action: 'qtime_warned',
            at: '2026-10-14T07:00:00Z',
            details: { rule: 'QT-ETCH', step_seq: 30, overdue_seconds: 600 },
          },
        ]}
      />
    )
    await expect
      .element(s.getByText('Q-Time 预警', { exact: true }))
      .toBeVisible()
    await expect
      .element(s.getByText(/规则 QT-ETCH · 工步 30 · 已超出预警 10 分/))
      .toBeVisible()
  })
})
