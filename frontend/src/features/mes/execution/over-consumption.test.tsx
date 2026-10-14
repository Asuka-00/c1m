import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { MesRow } from '@/lib/api/mes/common'
import { HistoryTimeline } from './lot-trace'
import { overLineText, overWarningText } from './over-consumption'

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('F4 超量与转换', () => {
  it('超量明细文本：数字和定点字符串都按十进制显示', () => {
    expect(
      overLineText({
        material: 'AU',
        actual: '1.500000',
        planned: 1e-6,
        uom: 'g',
        excess: '1.499999',
      })
    ).toBe('AU 1.5 / 0.000001 g（超 1.499999）')
    expect(overWarningText([])).toBeNull()
    expect(overWarningText([{ code: 'other', lines: [{}] }])).toBeNull()
  })

  it('批次履历：转换行（去向 / 来源 / die 数）和超量行，三语有翻译', async () => {
    const rows = [
      {
        id: 'h1',
        action: 'bom_over_consumption',
        at: '2026-10-14T07:00:00Z',
        qty: 25,
        details: {
          lines: [
            {
              material: 'AU',
              actual: 0.35,
              planned: 0.3,
              uom: 'g',
              excess: 0.05,
            },
          ],
        },
      },
      {
        id: 'h2',
        action: 'transform',
        at: '2026-10-14T06:00:00Z',
        qty: 25,
        to_status: 'converted',
        details: { transform_id: 't1', role: 'input', to: ['S1', 'S2'] },
      },
      {
        id: 'h3',
        action: 'transform',
        at: '2026-10-14T06:00:00Z',
        qty: 44,
        details: {
          transform_id: 't1',
          role: 'output',
          from: ['WF001-01', 'WF001-02'],
          die_qty: 44,
        },
      },
    ] as unknown as MesRow[]
    const s = await render(<HistoryTimeline rows={rows} />)
    const tl = s.getByTestId('timeline')
    await expect.element(tl).toHaveTextContent('BOM 超量用料')
    await expect.element(tl).toHaveTextContent('单位转换')
    await expect
      .element(s.getByTestId('over-lines'))
      .toHaveTextContent('AU 0.35 / 0.3 g（超 0.05）')
    await expect
      .element(tl)
      .toHaveTextContent(t('mes.over.transformTo', { list: 'S1, S2' }))
    await expect
      .element(tl)
      .toHaveTextContent(
        t('mes.over.transformFrom', { list: 'WF001-01, WF001-02' })
      )
    await expect
      .element(tl)
      .toHaveTextContent(t('mes.over.dieQty', { n: '44' }))
    for (const lng of ['en', 'ja']) {
      await i18n.changeLanguage(lng)
      for (const k of ['transform', 'bom_over_consumption'])
        expect(i18n.exists(`mes.enum.history_action.${k}`)).toBe(true)
    }
  })
})
