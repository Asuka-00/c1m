import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CheckResult } from '@/lib/api/mes/execution'
import { daysUntil } from '@/features/mes/common/due'
import {
  operatorQualMessage,
  pickQual,
  qualState,
} from '@/features/mes/execution/operator-qual'
import { isoDay } from '@/features/mes/execution/report-utils'
import {
  addDays,
  DEFAULT_SITE_TZ,
  getSiteTz,
  resolveSiteTz,
  setSiteTz,
  siteDate,
  siteListTz,
  siteToday,
  toSiteDate,
} from './site-tz'

// 台北 2026-10-15 03:00 = UTC 2026-10-14 19:00（UTC 还是前一天）
const TPE_0300 = new Date('2026-10-14T19:00:00Z')
// 台北 2026-10-15 00:00 / 07:59:59 两个边界
const TPE_0000 = new Date('2026-10-14T16:00:00Z')
const TPE_0759 = new Date('2026-10-14T23:59:59Z')

afterEach(() => {
  setSiteTz(DEFAULT_SITE_TZ)
  vi.useRealTimers()
})

describe('站点日期（D75）', () => {
  it('台北 00:00–08:00 时站点今天已是新的一天，UTC 日期还是前一天', () => {
    for (const at of [TPE_0000, TPE_0300, TPE_0759]) {
      expect(at.toISOString().slice(0, 10)).toBe('2026-10-14')
      expect(siteToday(at, 'Asia/Taipei')).toBe('2026-10-15')
    }
    expect(siteToday(new Date('2026-10-15T00:00:00Z'), 'Asia/Taipei')).toBe(
      '2026-10-15'
    )
  })

  it('站点时区与浏览器时区无关', () => {
    // 同一时刻：台北 10-15，洛杉矶 10-14，UTC 10-14
    expect(siteDate(TPE_0300, 'Asia/Taipei')).toBe('2026-10-15')
    expect(siteDate(TPE_0300, 'America/Los_Angeles')).toBe('2026-10-14')
    expect(siteDate(TPE_0300, 'UTC')).toBe('2026-10-14')
    expect(siteDate(new Date('2026-10-15T12:30:00Z'), 'Asia/Tokyo')).toBe(
      '2026-10-15'
    )
  })

  it('无效时区回落 Asia/Taipei', () => {
    expect(setSiteTz('Mars/Base')).toBe('Asia/Taipei')
    expect(setSiteTz(null)).toBe('Asia/Taipei')
    expect(setSiteTz('UTC')).toBe('UTC')
    expect(getSiteTz()).toBe('UTC')
    expect(siteDate(TPE_0300, 'bad/tz')).toBe('2026-10-15')
  })

  it('addDays / toSiteDate', () => {
    expect(addDays('2026-10-01', -1)).toBe('2026-09-30')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(toSiteDate('2026-10-14')).toBe('2026-10-14')
    expect(toSiteDate('2026-10-14T19:00:00Z', 'Asia/Taipei')).toBe('2026-10-15')
    expect(toSiteDate('2026-10-15T01:00:00+08:00', 'UTC')).toBe('2026-10-14')
    expect(toSiteDate('2026-10-14T23:00:00', 'Asia/Taipei')).toBe('2026-10-14')
  })
})

describe('site_tz 来源（D75）', () => {
  const sites = [
    { code: 'S2', timezone: 'Asia/Tokyo', is_active: true },
    { code: 'S0', timezone: 'UTC', is_active: false },
    { code: 'S1', timezone: 'America/Los_Angeles' },
  ]
  it('会话 site_tz 优先，其次第一个启用厂区（按编码），最后 Asia/Taipei', () => {
    expect(resolveSiteTz([{ site_tz: 'Europe/Berlin' }], sites)).toBe(
      'Europe/Berlin'
    )
    expect(
      resolveSiteTz([null, { tenant: { site_tz: 'Asia/Tokyo' } }], sites)
    ).toBe('Asia/Tokyo')
    expect(resolveSiteTz([{ site_tz: 'bad' }], sites)).toBe(
      'America/Los_Angeles'
    )
    expect(resolveSiteTz([], [])).toBe('Asia/Taipei')
    expect(resolveSiteTz([], undefined)).toBe('Asia/Taipei')
  })
  it('兼容 tenant_tz / tz 字段名，跳过无效时区', () => {
    expect(siteListTz([{ code: 'A', tenant_tz: 'Asia/Tokyo' }])).toBe(
      'Asia/Tokyo'
    )
    expect(siteListTz([{ code: 'A', tz: 'UTC' }])).toBe('UTC')
    expect(
      siteListTz([
        { code: 'A', timezone: 'x/y' },
        { code: 'B', timezone: 'UTC' },
      ])
    ).toBe('UTC')
    expect(siteListTz([{ code: 'A' }])).toBeNull()
  })
})

describe('到期判断按站点日期（台北 0–8 点固定时钟）', () => {
  it('daysUntil：昨天到期为 -1，今天到期为 0', () => {
    expect(daysUntil('2026-10-14', TPE_0300, 'Asia/Taipei')).toBe(-1)
    expect(daysUntil('2026-10-15', TPE_0300, 'Asia/Taipei')).toBe(0)
    // 同一时刻站点在洛杉矶：10-14 还是今天
    expect(daysUntil('2026-10-14', TPE_0300, 'America/Los_Angeles')).toBe(0)
  })

  it('daysUntil 默认用当前站点时区和系统时钟', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(TPE_0300)
    setSiteTz('Asia/Taipei')
    expect(daysUntil('2026-10-14')).toBe(-1)
    expect(daysUntil('2026-10-15')).toBe(0)
    expect(isoDay()).toBe('2026-10-15')
    expect(isoDay(-6)).toBe('2026-10-09')
    setSiteTz('UTC')
    expect(daysUntil('2026-10-14')).toBe(0)
    expect(isoDay()).toBe('2026-10-14')
  })

  it('资质：昨天到期必须是已过期，今天到期仍有效（临期）', () => {
    const y = {
      id: 'y',
      is_active: true,
      expires_on: '2026-10-14',
      operation_id: 'op',
    }
    const d = {
      id: 'd',
      is_active: true,
      expires_on: '2026-10-15',
      operation_id: 'op',
    }
    expect(qualState(y, TPE_0300, 30, 'Asia/Taipei')).toBe('expired')
    expect(qualState(d, TPE_0300, 30, 'Asia/Taipei')).toBe('expiring')
    expect(pickQual([y], 'op', null, TPE_0300, 'Asia/Taipei')).toBeNull()
    expect(pickQual([y, d], 'op', null, TPE_0300, 'Asia/Taipei')).toBe(d)
  })

  it('operatorQualMessage：临期提示按站点日期显示', () => {
    const r = {
      check_type: 'operator_qualified',
      result: 'pass',
      data: { expires: '2026-10-15T15:00:00Z', warn_days: 30 },
    } as unknown as CheckResult
    // UTC 15:00 = 台北 23:00，仍是 10-15
    expect(operatorQualMessage(r, TPE_0300, 'Asia/Taipei')).toContain(
      '2026-10-15'
    )
    // 换算到台北是 10-16
    const r2 = {
      ...r,
      data: { expires: '2026-10-15T17:00:00Z', warn_days: 30 },
    } as unknown as CheckResult
    expect(operatorQualMessage(r2, TPE_0300, 'Asia/Taipei')).toContain(
      '2026-10-16'
    )
  })
})
