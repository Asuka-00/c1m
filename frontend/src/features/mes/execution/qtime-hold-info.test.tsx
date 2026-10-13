import { t } from '@/i18n'
import en from '@/i18n/locales/en.json'
import ja from '@/i18n/locales/ja.json'
import zh from '@/i18n/locales/zh-CN.json'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { fmtOverdue, hasQtimeInfo } from './qtime-hold'
import { QtimeHoldInfo } from './qtime-hold-info'

const full = {
  qtime_rule_id: 'R-1',
  qtime_from_step_id: 'S1',
  qtime_to_step_id: 'S2',
  qtime_overdue_seconds: 5400,
}

describe('Q-Time Hold 信息（D20）', () => {
  it('超时秒数格式化为小时 / 分钟', () => {
    expect(fmtOverdue(5400)).toBe(
      t('mes.qtimeHold.hoursMinutes', { h: 1, m: 30 })
    )
    expect(fmtOverdue(7200)).toBe(t('mes.qtimeHold.hours', { h: 2 }))
    expect(fmtOverdue(90)).toBe(t('mes.qtimeHold.minutes', { m: 2 }))
    expect(fmtOverdue(5)).toBe(t('mes.qtimeHold.minutes', { m: 1 }))
  })

  it('有字段时显示超时、起止工步（可解析为名称）与规则', async () => {
    const s = await render(
      <QtimeHoldInfo hold={full} steps={{ S1: '10 · ETCH' }} />
    )
    const text = s.container.textContent ?? ''
    expect(text).toContain(
      t('mes.qtimeHold.overdue', { time: fmtOverdue(5400) })
    )
    expect(text).toContain(
      t('mes.qtimeHold.steps', { from: '10 · ETCH', to: 'S2' })
    )
    expect(text).toContain('R-1')
  })

  it('字段为 null 或缺失时不渲染', async () => {
    const nulls = {
      qtime_rule_id: null,
      qtime_from_step_id: null,
      qtime_to_step_id: null,
      qtime_overdue_seconds: null,
    }
    expect(hasQtimeInfo(nulls)).toBe(false)
    expect(hasQtimeInfo({})).toBe(false)
    const a = await render(<QtimeHoldInfo hold={nulls} />)
    expect(
      a.container.querySelector('[data-testid=qtime-hold-info]')
    ).toBeNull()
    const b = await render(<QtimeHoldInfo hold={{}} />)
    expect(
      b.container.querySelector('[data-testid=qtime-hold-info]')
    ).toBeNull()
  })

  it('中英日都有文案', () => {
    for (const l of [zh, en, ja])
      for (const k of [
        'overdue',
        'steps',
        'rule',
        'minutes',
        'hours',
        'hoursMinutes',
      ])
        expect((l.mes.qtimeHold as Record<string, string>)[k]).toBeTruthy()
  })

  it('优先显示后端返回的工步名，为空时退回工步列表 / id', async () => {
    const a = await render(
      <QtimeHoldInfo
        hold={{
          ...full,
          qtime_from_step_name: '10 CLEAN',
          qtime_to_step_name: '20 o2',
        }}
        steps={{ S1: 'list-name' }}
      />
    )
    expect(a.container.textContent).toContain(
      t('mes.qtimeHold.steps', { from: '10 CLEAN', to: '20 o2' })
    )
    await a.unmount()
    const b = await render(
      <QtimeHoldInfo
        hold={{ ...full, qtime_from_step_name: null, qtime_to_step_name: '' }}
        steps={{ S1: 'list-name' }}
      />
    )
    expect(b.container.textContent).toContain(
      t('mes.qtimeHold.steps', { from: 'list-name', to: 'S2' })
    )
  })
})
