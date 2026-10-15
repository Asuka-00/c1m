import i18n, { LANGUAGES } from '@/i18n'
import { describe, expect, it } from 'vitest'
import {
  BACKEND_MENU_KEYS,
  PENDING_MENU_KEYS,
  PLATFORM_MENU_KEYS,
} from './menu-keys.fixture'

const ALL = [...BACKEND_MENU_KEYS, ...PENDING_MENU_KEYS, ...PLATFORM_MENU_KEYS]

describe('菜单 key 三语翻译', () => {
  it.each(LANGUAGES)('%s 语言包包含全部后端菜单 key 的 menu.<key>', (lng) => {
    const missing = ALL.filter(
      (k) => !i18n.exists(`menu.${k}`, { lng, fallbackLng: [] })
    )
    expect(missing).toEqual([])
  })
})
