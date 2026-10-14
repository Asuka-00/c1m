import i18n, { LANGUAGES } from '@/i18n'
import { describe, expect, it } from 'vitest'
import { COMPONENTS } from '@/features/shell/dynamic/registry'
import {
  BACKEND_MENU_KEYS,
  MENU_KEY_ITEMS,
  PENDING_MENU_KEYS,
  PLATFORM_MENU_KEYS,
  TAB_ONLY_MENU_KEYS,
} from './menu-keys.fixture'
import data from './menu-keys.json'

const ALL = [
  ...new Set([
    ...BACKEND_MENU_KEYS,
    ...PENDING_MENU_KEYS,
    ...PLATFORM_MENU_KEYS,
  ]),
]
/** 菜单 key 用下划线、地址用连字符：比对前统一换成连字符（FE-03）。 */
const norm = (k: string) => k.replace(/_/g, '-')

describe('菜单 key 三语翻译', () => {
  it.each(LANGUAGES)('%s 语言包包含全部后端菜单 key 的 menu.<key>', (lng) => {
    const missing = ALL.filter(
      (k) => !i18n.exists(`menu.${k}`, { lng, fallbackLng: [] })
    )
    expect(missing).toEqual([])
  })
})

describe('menu-keys.json 一致性（后端 46e3da6）', () => {
  it('条数与 count 一致、key 唯一、i18n_key 为 menu.<key>', () => {
    expect(MENU_KEY_ITEMS.length).toBe(data.count)
    expect(new Set(MENU_KEY_ITEMS.map((i) => i.key)).size).toBe(data.count)
    for (const i of MENU_KEY_ITEMS) expect(i.i18n_key).toBe(`menu.${i.key}`)
  })

  it('每项三种语言标题都有（后端 JSON）', () => {
    const bad = MENU_KEY_ITEMS.filter((i) =>
      LANGUAGES.some((l) => !i.titles[l]?.trim())
    ).map((i) => i.key)
    expect(bad).toEqual([])
  })

  it('派生分组覆盖全部 key，页签都属于 workspace', () => {
    expect(BACKEND_MENU_KEYS.length + PLATFORM_MENU_KEYS.length).toBe(
      data.count
    )
    expect(TAB_ONLY_MENU_KEYS.every((k) => BACKEND_MENU_KEYS.includes(k))).toBe(
      true
    )
  })

  it('菜单 / 页签引用的组件前端都已注册（路由能渲染）', () => {
    const missing = MENU_KEY_ITEMS.map((i) => i.component)
      .filter(
        (c): c is string =>
          !!c && !c.startsWith('mes:') && c !== 'tabs' && c !== 'tree'
      )
      .filter((c) => !(c in COMPONENTS))
    expect(missing).toEqual([])
  })

  it('/mes/ 地址与 key 对齐（下划线换连字符）；页签地址等于父菜单地址', () => {
    const byKey = new Map(MENU_KEY_ITEMS.map((i) => [i.key, i]))
    const bad: string[] = []
    for (const i of MENU_KEY_ITEMS) {
      if (i.kind === 'item' && i.path?.startsWith('/mes/'))
        if (norm(`mes-${i.path.slice(5)}`) !== norm(i.key)) bad.push(i.key)
      if (i.kind === 'tab' && byKey.get(i.parent ?? '')?.path !== i.path)
        bad.push(i.key)
    }
    expect(bad).toEqual([])
  })

  it('父节点都存在', () => {
    const keys = new Set(MENU_KEY_ITEMS.map((i) => i.key))
    const bad = MENU_KEY_ITEMS.filter((i) => i.parent && !keys.has(i.parent))
    expect(bad.map((i) => i.key)).toEqual([])
  })
})
