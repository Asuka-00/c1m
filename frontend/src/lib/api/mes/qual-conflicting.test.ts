import { describe, expect, it } from 'vitest'
import { mockQualWriteApi as qual, resetQualHistoryMock } from './qual-history'

// 后端格式：type value_error，loc ["body","is_active"]，ctx {reason, fields}
describe('conflicting_fields 与后端同形', () => {
  it.each(['q1', 'nope'])('%s：请求体阶段 422，ctx 带 fields', async (id) => {
    resetQualHistoryMock()
    const e = await qual
      .update(id, { is_active: false, expires_on: '2026-12-31' }, 'CF')
      .catch((x) => x)
    expect(e.response.status).toBe(422)
    expect(e.response.data.detail).toEqual([
      expect.objectContaining({
        type: 'value_error',
        loc: ['body', 'is_active'],
        ctx: {
          reason: 'conflicting_fields',
          fields: ['is_active', 'expires_on'],
        },
      }),
    ])
  })
})
