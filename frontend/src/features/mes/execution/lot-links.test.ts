import { describe, expect, it } from 'vitest'
import { TAB_ONLY_MENU_KEYS } from '@/components/layout/menu-keys.fixture'
import { lotPageLink } from './lot-links'

const TAB_ONLY = new Set<string>(TAB_ONLY_MENU_KEYS)

/** 收集源码里所有拼出来的页面路径：_splat 字面量与 lotPageLink 的 page 参数。 */
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
    for (const m of src.matchAll(/lotPageLink\(\s*'([\w-]+)'/g))
      hits.push({ file, path: lotPageLink(m[1] as never, 'x').params._splat })
    for (const m of src.matchAll(/page=['"]([\w-]+)['"]/g))
      hits.push({ file, path: lotPageLink(m[1] as never, 'x').params._splat })
  }
  return hits
}

const toKey = (path: string) =>
  path.startsWith('mes/') ? `mes-${path.slice(4)}` : path

describe('页面跳转', () => {
  it('批次履历跳 mes/lot-history 的 mes-lot-trace 页签', () => {
    expect(lotPageLink('lot-trace', 7)).toMatchObject({
      params: { _splat: 'mes/lot-history' },
      search: { tab: 'mes-lot-trace', lot: '7' },
    })
    expect(lotPageLink('lot-console', 7)).toMatchObject({
      params: { _splat: 'mes/lot-console' },
      search: { lot: '7' },
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
