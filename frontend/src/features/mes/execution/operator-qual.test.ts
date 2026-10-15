import { AxiosError, AxiosHeaders } from 'axios'
import i18n from '@/i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/lib/api/client'
import type { CheckResult } from '@/lib/api/mes/execution'
import { qualExpiringApi } from '@/lib/api/mes/qual-expiring'
import { checkMessage } from './check-message'
import { pickQual, qualState, warnDaysOf } from './operator-qual'

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
      'op1 不具备工序 WB 的有效资质，不能进站，且不可放行。请先取得或续期资质。'
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

describe('P3 人员资质（D62 / D64）', () => {
  it('warn_days 下发优先，读不到用 30', () => {
    expect(warnDaysOf(7)).toBe(7)
    expect(warnDaysOf('14')).toBe(14)
    expect(warnDaysOf(undefined)).toBe(30)
    expect(warnDaysOf('x')).toBe(30)
    expect(warnDaysOf(0)).toBe(30)
    expect(warnDaysOf(-5)).toBe(30)
    expect(warnDaysOf(1)).toBe(1)
    expect(warnDaysOf(365)).toBe(365)
    expect(warnDaysOf(366)).toBe(30)
    expect(warnDaysOf(7.5)).toBe(30)
    expect(warnDaysOf(null)).toBe(30)
    expect(qualState({ id: 'q', expires_on: '2026-10-24' }, today, 7)).toBe(
      'valid'
    )
  })

  it('工序+设备类型优先于只按工序；过期 / 停用不选；当天有效', () => {
    const rows = [
      { id: 'a', operation_id: 'op', equipment_type_id: null },
      {
        id: 'b',
        operation_id: 'op',
        equipment_type_id: 'et1',
        expires_on: '2026-10-14',
      },
      {
        id: 'c',
        operation_id: 'op',
        equipment_type_id: 'et2',
        expires_on: '2026-10-13',
      },
    ]
    expect(pickQual(rows, 'op', 'et1', today)?.id).toBe('b')
    expect(pickQual(rows, 'op', 'et2', today)?.id).toBe('a')
    expect(pickQual(rows, 'op', null, today)?.id).toBe('a')
    expect(pickQual(rows, 'other', 'et1', today)).toBeNull()
  })

  it('check_blocked 多原因：列出 reasons[]，单原因取 reason', () => {
    const base = { check_type: 'reticle', result: 'block', message: 'raw' }
    expect(
      checkMessage({
        ...base,
        reason: 'r1',
        reasons: ['r1', { message: 'r2' }],
      } as unknown as CheckResult)
    ).toBe('r1；r2')
    expect(
      checkMessage({ ...base, reason: 'only' } as unknown as CheckResult)
    ).toBe('only')
    expect(checkMessage(base as unknown as CheckResult)).toBe('raw')
  })

  it('汇总接口路径（默认不传 days），404 回退示例数据', async () => {
    const e = new AxiosError('404')
    e.response = {
      status: 404,
      data: {},
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
    const get = vi.spyOn(http, 'get').mockRejectedValueOnce(e)
    const r = await qualExpiringApi.list()
    expect(get.mock.calls[0][0]).toBe('/mes/exec/operator-qual/expiring')
    expect(get.mock.calls[0][1]).toEqual({ params: { days: undefined } })
    expect(r.mock).toBe(true)
    expect(r.warn_days).toBe(30)
    get.mockRestore()
  })
})
