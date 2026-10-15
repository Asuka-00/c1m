import { describe, expect, it } from 'vitest'
import { TAB_ONLY_MENU_KEYS } from '@/components/layout/menu-keys.fixture'
import { lotPageLink } from './lot-links'

/**
 * 菜单 key 用下划线（`mes-check_rule`），页面地址用连字符（`/mes/check-rule`）：
 * 两边都把下划线换成连字符再比对（FE-03）。
 */
const norm = (k: string) => k.replace(/_/g, '-')
const TAB_ONLY = new Set<string>(TAB_ONLY_MENU_KEYS.map(norm))

/**
 * 从一份源码里收集拼出来的页面路径：_splat 字面量、lotPageLink 的 page 参数、
 * `page=` 属性，以及 `<Kpi to='mes/...'>` 这类 `to=` 相对菜单路径（FE-03）。
 */
function targetsIn(file: string, src: string) {
  const hits: { file: string; path: string }[] = []
  for (const m of src.matchAll(
    /_splat:?\s*[:=]?\s*\{?\s*['"`]([a-z][\w/-]*)['"`]/g
  ))
    hits.push({ file, path: m[1] })
  for (const m of src.matchAll(/lotPageLink\(\s*'([\w-]+)'/g))
    hits.push({ file, path: lotPageLink(m[1] as never, 'x').params._splat })
  for (const m of src.matchAll(/page=['"]([\w-]+)['"]/g))
    hits.push({ file, path: lotPageLink(m[1] as never, 'x').params._splat })
  for (const m of src.matchAll(/\bto=\{?\s*['"`](mes\/[\w/-]+)['"`]/g))
    hits.push({ file, path: m[1] })
  return hits
}

/** 收集全部源码（不含测试与 fixture）里拼出来的页面路径。 */
function collectTargets() {
  const files = import.meta.glob('/src/**/*.{ts,tsx}', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>
  const hits: { file: string; path: string }[] = []
  for (const [file, src] of Object.entries(files)) {
    if (/\.test\.|fixture/.test(file)) continue
    hits.push(...targetsIn(file, src))
  }
  return hits
}

const toKey = (path: string) =>
  norm(path.startsWith('mes/') ? `mes-${path.slice(4)}` : path)

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

  it('下划线 key 与连字符地址能对上；Kpi 的 to= 也被收集', () => {
    expect(TAB_ONLY.has(toKey('mes/check-rule'))).toBe(true)
    expect(TAB_ONLY.has(toKey('mes/check_rule'))).toBe(true)
    const kpi = targetsIn(
      'x.tsx',
      `<Kpi title='a' icon={X} to='mes/check-rule'>`
    )
    expect(kpi.map((h) => h.path)).toEqual(['mes/check-rule'])
    expect(kpi.filter((h) => TAB_ONLY.has(toKey(h.path)))).toHaveLength(1)
    // 首页 KPI 卡片的跳转确实被纳入了全量检查
    expect(
      collectTargets().some(
        (h) => h.file.endsWith('home-kpis.tsx') && h.path === 'mes/eqp-board'
      )
    ).toBe(true)
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
