import { describe, expect, it } from 'vitest'
import { mesErrorMessage } from '@/features/mes/common/required'
import { qualReasonMessage } from '@/features/mes/execution/qual-history-format'
import { errorMessage } from '../client'
import {
  mockQualHistoryApi as hist,
  mockQualWriteApi as api,
  resetQualHistoryMock,
} from './qual-history'

// D88 补充一
describe('D88 补充一', () => {
  it('履历 rows[].at 一律带 Z 的 UTC', async () => {
    resetQualHistoryMock()
    await api.update(
      'q1',
      { is_active: false, reason_id: 'R', comment: 'c' },
      'k1'
    )
    const rows = (await hist.history('q1')).rows
    expect(rows.length).toBeGreaterThan(1)
    for (const r of rows)
      expect(r.at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/)
  })
  it('通用 404 detail 为字符串 "Record not found"，提示只看状态码也能正常显示', async () => {
    resetQualHistoryMock()
    const e = await api
      .update('nope', { certified_on: '2026-01-01' }, 'k2')
      .catch((x) => x)
    expect(e.response.status).toBe(404)
    expect(e.response.data.detail).toBe('Record not found')
    expect(qualReasonMessage(e)).toBeNull()
    const m = mesErrorMessage(e, undefined)
    expect(m).toBeTruthy()
    expect(m).toBe(errorMessage(e))
    expect(m).not.toMatch(/\[object Object\]|undefined/)
  })
})
