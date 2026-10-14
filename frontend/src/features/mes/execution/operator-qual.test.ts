import i18n from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import type { CheckResult } from '@/lib/api/mes/execution'
import { checkMessage } from './check-message'
import { qualState } from './operator-qual'

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

const today = new Date(2026, 9, 14)

describe('P3 人员资质草案', () => {
  it('有效期状态：停用、过期、30 天内临期、有效、长期', () => {
    expect(
      qualState({ id: 'q', is_active: false, expires_on: '2020-01-01' }, today)
    ).toBe('inactive')
    expect(
      qualState({ id: 'q', is_active: true, expires_on: '2026-10-13' }, today)
    ).toBe('expired')
    expect(
      qualState({ id: 'q', is_active: true, expires_on: '2026-10-14' }, today)
    ).toBe('expiring')
    expect(
      qualState({ id: 'q', is_active: true, expires_on: '2026-11-13' }, today)
    ).toBe('expiring')
    expect(
      qualState({ id: 'q', is_active: true, expires_on: '2026-11-14' }, today)
    ).toBe('valid')
    expect(
      qualState({ id: 'q', is_active: true, expires_on: null }, today)
    ).toBe('valid')
  })

  it('operator_qualified 不合格：本地化不能进站说明', () => {
    const r = {
      check_type: 'operator_qualified',
      result: 'fail',
      message: 'op1 not qualified for WB',
      data: { user: 'op1', operation: 'WB' },
    } as unknown as CheckResult
    expect(checkMessage(r)).toBe(
      'op1 不具备工序 WB 的有效资质，不能进站。请先取得或续期资质。'
    )
  })

  it('通过且远未到期：沿用后端原文', () => {
    const r = {
      check_type: 'operator_qualified',
      result: 'pass',
      message: 'ok',
      data: { user: 'op1', operation: 'WB', expires: '2099-01-01' },
    } as unknown as CheckResult
    expect(checkMessage(r)).toBe('ok')
  })
})
