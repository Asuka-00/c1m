import i18n, { LANGUAGES } from '@/i18n'
import { describe, expect, it } from 'vitest'
import { ROW_PANELS } from './registry'

describe('详情面板标题三语翻译', () => {
  it.each(LANGUAGES)('%s 语言包包含全部 mes.panel.<entity>', (lng) => {
    const missing = Object.keys(ROW_PANELS).filter(
      (k) => !i18n.exists(`mes.panel.${k}`, { lng, fallbackLng: [] })
    )
    expect(missing).toEqual([])
  })
})
