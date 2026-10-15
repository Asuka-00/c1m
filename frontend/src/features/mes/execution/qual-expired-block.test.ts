import { t } from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import type { CheckResult } from '@/lib/api/mes/execution'
import {
  mockTrackInQualCheck,
  resetQualHistoryMock,
  setQualMockNow,
} from '@/lib/api/mes/qual-history'
import { operatorQualMessage } from './operator-qual'

beforeEach(() => resetQualHistoryMock())

describe('40e4342 过期进站 409 check_blocked operator_qualified', () => {
  it('mock 形状：顶层 ctx {qual_id, expires_on}，data 带 reason=expired', () => {
    setQualMockNow(() => new Date('2026-10-12T02:00:00Z'))
    const e = mockTrackInQualCheck('op2', 'WB', 'WB-ASM')!
    const r = (e.response!.data as { detail: { results: CheckResult[] } })
      .detail.results[0]
    expect(r).toMatchObject({
      check_type: 'operator_qualified',
      overridable: false,
      ctx: { qual_id: 'q2', expires_on: '2026-10-10' },
      data: { reason: 'expired', expires_on: '2026-10-10' },
    })
    expect(operatorQualMessage(r)).toBe(
      t('mes.qual.expiredBlock', { user: 'op2', op: 'WB', date: '2026-10-10' })
    )
  })
  it('无资质仍是 notQualified', () => {
    const r = {
      check_type: 'operator_qualified',
      result: 'block',
      data: {
        user: 'u',
        operation: 'OP',
        reason: 'not_qualified',
        expires_on: null,
      },
      ctx: { qual_id: null, expires_on: null },
    } as unknown as CheckResult
    expect(operatorQualMessage(r)).toBe(
      t('mes.qual.notQualified', { user: 'u', op: 'OP' })
    )
  })
})
