import { t } from '@/i18n'
import en from '@/i18n/locales/en.json'
import ja from '@/i18n/locales/ja.json'
import zh from '@/i18n/locales/zh-CN.json'
import { describe, expect, it } from 'vitest'
import { reasonLabel, reasonName, reasonOptLabel } from './labels'

describe('原因码本地化（M1：qtime_expired）', () => {
  it('内置原因码用本地化名称，其他沿用主数据名称', () => {
    const qt = t('mes.reasonCode.qtime_expired')
    expect(reasonName('qtime_expired', 'whatever')).toBe(qt)
    expect(reasonName('QC01', '外观')).toBe('外观')
    expect(reasonOptLabel({ code: 'qtime_expired' })).toBe(
      `qtime_expired · ${qt}`
    )
    expect(reasonOptLabel({ code: 'QC01' })).toBe('QC01')
    expect(reasonLabel('qtime_expired · Q-Time')).toBe(`qtime_expired · ${qt}`)
    expect(reasonLabel('QC01 · 外观')).toBe('QC01 · 外观')
    expect(reasonLabel(null)).toBe('')
  })

  it('中英日都有 qtime_expired 文案', () => {
    for (const l of [zh, en, ja])
      expect(l.mes.reasonCode.qtime_expired).toBeTruthy()
  })
})
