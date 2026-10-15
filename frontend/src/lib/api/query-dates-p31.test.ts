import { describe, expect, it } from 'vitest'
import type { MesEntity } from './mes/common'
import { mockListQueryDateCheck, normalizeListQuery } from './query-dates'

// QA P3-1：字段名本身以 _from/_to 结尾时按字段名匹配，不当范围后缀剥掉
const e = {
  code: 'product_route',
  fields: [
    { name: 'effective_from', column: 'effective_from', type: 'date' },
    { name: 'effective_to', column: 'effective_to', type: 'date' },
    { name: 'valid_to', column: 'valid_to', type: 'datetime' },
    { name: 'valid', column: 'valid', type: 'datetime' },
  ],
} as unknown as MesEntity

describe('P3-1 effective_from / effective_to 等值筛选', () => {
  it('mock 校验不再跳过：非法日期 422 pattern', () => {
    for (const k of ['effective_from', 'effective_to']) {
      const err = mockListQueryDateCheck(e, { [k]: '2026/10/01' })
      expect(err?.response?.status).toBe(422)
      expect(
        (err?.response?.data as { detail: { loc: string[] }[] }).detail[0].loc
      ).toEqual(['query', k])
    }
    expect(mockListQueryDateCheck(e, { effective_to: '2026-10-01' })).toBeNull()
  })
  it('归一按字段类型处理；字段名 valid_to 是等值，不按范围上界', () => {
    const q = normalizeListQuery(e, {
      valid_to: '2026-10-01',
      valid: '2026-10-01',
    })
    expect(q.valid_to).toBe(q.valid)
    // 范围后缀仍然生效：valid_from/valid 的 _to 才是上界
    const r = normalizeListQuery(
      { code: 'x', fields: [e.fields[3]] } as unknown as MesEntity,
      { valid_from: '2026-10-01', valid_to: '2026-10-01' }
    )
    expect(r.valid_to).not.toBe(r.valid_from)
  })
})
