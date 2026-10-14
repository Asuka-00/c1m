import i18n, { t } from '@/i18n'
import { afterEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { CELLS } from './row-rules'

let n = 0
const cell = async (ent: string, f: string, r: Record<string, unknown>) => {
  const id = `c${n++}`
  const s = await render(
    <div data-testid={id}>{CELLS[ent][f]({ id: 'x', ...r })}</div>
  )
  return s.getByTestId(id)
}

afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('D58 补充：trigger / source 三语显示', () => {
  it.each([
    ['zh-CN', '设备事件', '模拟器'],
    ['en', 'Equipment event', 'Simulator'],
    ['ja', '設備イベント', 'シミュレータ'],
  ])('%s', async (lng, trig, sim) => {
    await i18n.changeLanguage(lng)
    await expect
      .element(await cell('e10_history', 'trigger', { trigger: 'equipment' }))
      .toHaveTextContent(trig)
    await expect
      .element(await cell('e10_history', 'source', { source: 'simulator' }))
      .toHaveTextContent(sim)
    await expect
      .element(await cell('alarm_log', 'source', { source: 'eap' }))
      .toHaveTextContent('EAP')
  })

  it('字段缺失显示「—」', async () => {
    await expect
      .element(await cell('e10_history', 'trigger', {}))
      .toHaveTextContent('—')
    await expect
      .element(await cell('alarm_log', 'source', { source: null }))
      .toHaveTextContent('—')
  })

  it('不再暗示报警会 Hold 批次', async () => {
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      expect(t('mes.alarm.clearDesc')).not.toMatch(/Hold|ホールド/i)
      // D59（752503e）：联动只有 none / set_state，旧 hold_* 标签已删
      expect(t('mes.enum.alarm_action.set_state')).not.toMatch(/Hold|ホールド/i)
      expect(i18n.exists('mes.enum.alarm_action.hold_lot')).toBe(false)
      expect(i18n.exists('mes.enum.alarm_action.hold_both')).toBe(false)
      expect(i18n.exists('mes.field.alarm_code.hold_reason')).toBe(false)
      expect(t('mes.field.alarm_code.target_state')).toBeTruthy()
      expect(t('mes.enum.e10_trigger.system')).toBeTruthy()
    }
  })
})

describe('E10 履历 trigger（752503e）', () => {
  it.each(['manual', 'equipment', 'system'])(
    'trigger=%s 三语有文案',
    async (v) => {
      for (const lng of ['zh-CN', 'en', 'ja']) {
        await i18n.changeLanguage(lng)
        const el = await cell('e10_history', 'trigger', { trigger: v })
        await expect
          .element(el)
          .toHaveTextContent(t(`mes.enum.e10_trigger.${v}`))
      }
    }
  )
})
