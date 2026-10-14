import i18n, { t } from '@/i18n'
import { afterEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { EXTRA_COLUMNS } from '@/features/mes/registry'

const ALARM_LOG_COLUMNS = EXTRA_COLUMNS.alarm_log

afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

let n = 0
const cell = async (i: number, r: Record<string, unknown>) => {
  const id = `c${n++}`
  const s = await render(
    <div data-testid={id}>{ALARM_LOG_COLUMNS[i].cell({ id: 'x', ...r })}</div>
  )
  return s.getByTestId(id)
}

describe('报警履历 state_changed / 跳过原因两列', () => {
  it('已注册到 alarm_log', () => {
    expect(ALARM_LOG_COLUMNS).toHaveLength(2)
  })

  it.each(['zh-CN', 'en', 'ja'])('%s 表头与单元格', async (lng) => {
    await i18n.changeLanguage(lng)
    expect(ALARM_LOG_COLUMNS.map((c) => c.header())).toEqual([
      t('mes.alarm.col.stateChanged'),
      t('mes.alarm.col.skipReason'),
    ])
    await expect
      .element(await cell(0, { state_changed: false }))
      .toHaveTextContent(t('mes.alarm.changed.no'))
    await expect
      .element(await cell(1, { state_skip_reason: 'already_in_state' }))
      .toHaveTextContent(t('mes.alarm.skip.already_in_state'))
  })

  it('无联动显示「—」，未知码原样', async () => {
    await expect.element(await cell(0, {})).toHaveTextContent('—')
    await expect.element(await cell(1, {})).toHaveTextContent('—')
    await expect
      .element(await cell(1, { state_skip_reason: 'new_code' }))
      .toHaveTextContent('new_code')
    await expect
      .element(await cell(0, { state_changed: true }))
      .toHaveTextContent(t('mes.alarm.changed.yes'))
  })
})
