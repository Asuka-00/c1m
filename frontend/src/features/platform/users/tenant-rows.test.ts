import { describe, expect, it } from 'vitest'
import { decodeRows, encodeRows } from './tenant-rows'

describe('tenant rows', () => {
  it('round-trips rows and drops tenant_name', () => {
    const rows = [{ tenant_id: 'a', tenant_name: 'A', roles: ['member'] }]
    expect(decodeRows(encodeRows(rows))).toEqual([
      { tenant_id: 'a', roles: ['member'] },
    ])
  })
  it('skips empty rows and dedupes tenants', () => {
    const v = encodeRows([
      { tenant_id: '', roles: ['member'] },
      { tenant_id: 'a', roles: [] },
      { tenant_id: 'a', roles: ['owner'] },
    ])
    expect(decodeRows(v)).toEqual([{ tenant_id: 'a', roles: ['owner'] }])
  })
})
