import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { DEFAULT_SITE_TZ, setSiteTz } from '@/lib/site-tz'
import {
  filterKeys,
  filterOptionsKey,
  FILTER_OPTIONS_SUFFIX,
  rangeParam,
} from './filter-defs'

describe('filterOptionsKey', () => {
  it('appends a dedicated suffix and keeps the caller prefix', () => {
    expect(filterOptionsKey({ name: 'x' })).toEqual([
      'filter-options',
      'x',
      FILTER_OPTIONS_SUFFIX,
    ])
    expect(
      filterOptionsKey({ name: 'e', optionsKey: ['notifications', 'meta'] })
    ).toEqual(['notifications', 'meta', FILTER_OPTIONS_SUFFIX])
  })

  // 回归：消息中心的类型筛选与订阅页的元数据查询曾共用 ['notifications','meta']，
  // 先打开订阅页后，筛选读到对象而非数组 → options.map 抛错 → 500 错误页
  it('never shares cache with a data query using the same key', () => {
    const qc = new QueryClient()
    const dataKey = ['notifications', 'meta']
    qc.setQueryData(dataKey, { event_types: [] })
    const optKey = filterOptionsKey({ name: 'event_type', optionsKey: dataKey })
    expect(qc.getQueryData(optKey)).toBeUndefined()
    // 按前缀失效仍能命中选项缓存
    qc.setQueryData(optKey, [{ value: 'a', label: 'A' }])
    expect(
      qc.getQueryCache().findAll({ queryKey: ['notifications'] }).length
    ).toBe(2)
  })
})

describe('date range filters', () => {
  it('expands to _from / _to URL keys', () => {
    expect(filterKeys({ type: 'daterange', name: 'at', label: 'x' })).toEqual([
      'at_from',
      'at_to',
    ])
    expect(filterKeys({ type: 'text', name: 'q' })).toEqual(['q'])
  })

  it('D77 半开区间：datetime _from 当天 0 点、_to 次日 0 点（站点时区带偏移），date 两头都含', () => {
    // 台北
    expect(rangeParam('2026-10-01', false)).toBe('2026-10-01T00:00:00+08:00')
    expect(rangeParam('2026-10-01', true)).toBe('2026-10-02T00:00:00+08:00')
    expect(rangeParam('2026-12-31', true)).toBe('2027-01-01T00:00:00+08:00')
    // date 字段：站点日期原样，两头都含
    expect(rangeParam('2026-10-01', true, 'date')).toBe('2026-10-01')
    expect(rangeParam('2026-10-01T05:00:00Z', false, 'date')).toBe('2026-10-01')
  })

  it('D77 洛杉矶夏令时切换：偏移按次日 0 点那一刻算', () => {
    const la = (v: string, end: boolean) =>
      rangeParam(v, end, 'datetime', 'America/Los_Angeles')
    // 3-07 结束 → 3-08 0 点仍是 PST
    expect(la('2026-03-07', false)).toBe('2026-03-07T00:00:00-08:00')
    expect(la('2026-03-07', true)).toBe('2026-03-08T00:00:00-08:00')
    // 3-08 当天切到 PDT：开始 -08:00，结束（3-09 0 点）-07:00
    expect(la('2026-03-08', false)).toBe('2026-03-08T00:00:00-08:00')
    expect(la('2026-03-08', true)).toBe('2026-03-09T00:00:00-07:00')
    // 11-01 当天切回 PST：开始 -07:00，结束（11-02 0 点）-08:00
    expect(la('2026-11-01', false)).toBe('2026-11-01T00:00:00-07:00')
    expect(la('2026-11-01', true)).toBe('2026-11-02T00:00:00-08:00')
    // 10-31 结束 → 11-01 0 点仍是 PDT
    expect(la('2026-10-31', true)).toBe('2026-11-01T00:00:00-07:00')
  })

  it('浏览器时区与站点不一致：一律按站点时区', () => {
    // 测试浏览器是台北，站点分别设成 UTC / Kolkata
    expect(rangeParam('2026-10-15', true, 'datetime', 'UTC')).toBe(
      '2026-10-16T00:00:00+00:00'
    )
    expect(rangeParam('2026-10-15', false, 'datetime', 'Asia/Kolkata')).toBe(
      '2026-10-15T00:00:00+05:30'
    )
    setSiteTz('America/Los_Angeles')
    try {
      expect(rangeParam('2026-10-15', true)).toBe('2026-10-16T00:00:00-07:00')
    } finally {
      setSiteTz(DEFAULT_SITE_TZ)
    }
  })
})
