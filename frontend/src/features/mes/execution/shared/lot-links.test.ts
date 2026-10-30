import { describe, expect, it } from 'vitest'
import { TAB_ONLY_MENU_KEYS } from '@/components/layout/menu-keys.fixture'
import { lotPageLink } from './lot-links'

const TAB_ONLY = new Set<string>(TAB_ONLY_MENU_KEYS)

/** 收集源码里所有拼出来的页面路径（_splat 字面量）。 */
function collectTargets() {
  const files = import.meta.glob('/src/**/*.{ts,tsx}', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>
  const hits: { file: string; path: string }[] = []
  for (const [file, src] of Object.entries(files)) {
    if (/\.test\.|fixture/.test(file)) continue
    for (const m of src.matchAll(
      /_splat:?\s*[:=]?\s*\{?\s*['"`]([a-z][\w/-]*)['"`]/g
    ))
      hits.push({ file, path: m[1] })
  }
  return hits
}

const toKey = (path: string) =>
  path.startsWith('mes/') ? `mes-${path.slice(4)}` : path

describe('页面跳转', () => {
  it('批次链接进操作台，履历等为操作台页签', () => {
    expect(lotPageLink(7)).toEqual({
      to: '/$',
      params: { _splat: 'mes/lot-console' },
      search: { lot: '7' },
    })
    expect(lotPageLink(7, 'history')).toMatchObject({
      params: { _splat: 'mes/lot-console' },
      search: { lot: '7', view: 'history' },
    })
  })

  it('源码里拼出的路径都不指向只作页签的 key', () => {
    const hits = collectTargets()
    expect(hits.length).toBeGreaterThan(10)
    const bad = hits.filter((h) => TAB_ONLY.has(toKey(h.path)))
    expect(bad).toEqual([])
  })

  it('不在 lotPageLink 之外用模板字符串拼 mes/${...} 路径', () => {
    const files = import.meta.glob('/src/**/*.{ts,tsx}', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>
    const bad = Object.entries(files)
      .filter(([f]) => !/\.test\.|lot-links\.ts$/.test(f))
      .filter(([, src]) => /_splat:?\s*[:=]?\s*\{?\s*`mes\/\$\{/.test(src))
      .map(([f]) => f)
    expect(bad).toEqual([])
  })
})
