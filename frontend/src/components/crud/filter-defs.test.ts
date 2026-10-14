import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
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

  it('datetime 字段按站点时区当天边界带偏移发送，date 字段只取前 10 位（D75）', () => {
    expect(rangeParam('2026-10-01', false)).toBe('2026-10-01T00:00:00+08:00')
    expect(rangeParam('2026-10-01', true)).toBe(
      '2026-10-01T23:59:59.999999+08:00'
    )
    expect(rangeParam('2026-10-01', true, 'date')).toBe('2026-10-01')
    expect(rangeParam('2026-10-01T05:00:00Z', false, 'date')).toBe('2026-10-01')
    // 浏览器时区（测试机台北）与站点不一致：按站点洛杉矶
    expect(
      rangeParam('2026-10-01', false, 'datetime', 'America/Los_Angeles')
    ).toBe('2026-10-01T00:00:00-07:00')
    expect(
      rangeParam('2026-12-01', true, 'datetime', 'America/Los_Angeles')
    ).toBe('2026-12-01T23:59:59.999999-08:00')
  })
})
