import en from '@/i18n/locales/en.json'
import ja from '@/i18n/locales/ja.json'
import zh from '@/i18n/locales/zh-CN.json'
import { describe, expect, it } from 'vitest'
import { canRunStage } from '../lot-rules'

describe('Hold 提示与 Track Out（decisions #2）', () => {
  it('提示文案说明 Hold 中仍可 Track Out', () => {
    for (const l of [zh, en, ja])
      expect(l.mes.exec.holdBlocks).toMatch(/Track Out/)
    expect(zh.mes.exec.holdBlocks).toMatch(/Move Out/)
    expect(en.mes.exec.holdBlocks).toMatch(/Move Out/)
  })

  it('与按钮条件一致：Hold 中仅 Track Out 可执行', () => {
    const lot = { lot_status: 'running', on_hold: true }
    expect(canRunStage(lot, 'track_out')).toBe(true)
    expect(canRunStage({ ...lot, lot_status: 'tracked_out' }, 'move_out')).toBe(
      false
    )
  })
})
