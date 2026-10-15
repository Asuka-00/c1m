import { describe, expect, it } from 'vitest'
import { clientList } from './client-list'
import type { ListParams } from './use-list-params'

const p = (over: Partial<ListParams>): ListParams =>
  ({
    page: 1,
    pageSize: 2,
    sortOrder: 'asc',
    filters: {},
    q: '',
    query: {},
    setFilter: () => {},
    setRange: () => {},
    set: () => {},
    ...over,
  }) as ListParams

const rows = [
  { code: 'A1', st: 'x', n: 3 },
  { code: 'B2', st: 'y', n: null },
  { code: 'A3', st: 'x', n: 1 },
]

describe('clientList', () => {
  it('searches, filters and pages', () => {
    const r = clientList(rows, p({ filters: { q: 'a', st: 'x' } }), {
      text: (x) => x.code,
    })
    expect(r.total).toBe(2)
    expect(r.rows.map((x) => x.code)).toEqual(['A1', 'A3'])
    expect(clientList(rows, p({ page: 2 })).rows).toHaveLength(1)
  })
  it('sorts with nulls last', () => {
    const r = clientList(rows, p({ pageSize: 9, sortBy: 'n' }))
    expect(r.rows.map((x) => x.code)).toEqual(['A3', 'A1', 'B2'])
  })
  it('uses custom match', () => {
    const r = clientList(rows, p({ filters: { big: '1' } }), {
      match: { big: (x) => (x.n ?? 0) > 2 },
    })
    expect(r.total).toBe(1)
  })
})
