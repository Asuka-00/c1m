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

  it('converts local days to inclusive instants for datetime fields', () => {
    const a = new Date(rangeParam('2026-10-01', false))
    const b = new Date(rangeParam('2026-10-01', true))
    expect([a.getHours(), a.getMinutes(), a.getDate()]).toEqual([0, 0, 1])
    expect([b.getHours(), b.getMinutes(), b.getDate()]).toEqual([23, 59, 1])
    expect(rangeParam('2026-10-01', true, 'date')).toBe('2026-10-01')
  })
})
