import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  mockReticleApi,
  resetReticleMock,
  setReticleMockNow,
  tooFarInFuture,
} from '@/lib/api/mes/reticle'
import { siteWallToIso } from '@/lib/site-tz'
import { reticleErrorMessage, validateAction } from './reticle-rules'

// 当前时间：台北 2026-10-15 10:00:00（UTC 02:00）
const NOW = Date.parse('2026-10-15T02:00:00Z')
const at = (mmss: string) => `2026-10-15T10:${mmss}+08:00`
let n = 0
const act = (
  id: string,
  a: Parameters<typeof mockReticleApi.act>[1],
  input: Parameters<typeof mockReticleApi.act>[2]
) => mockReticleApi.act(id, a, input, `d82-${++n}`)
const fail = async (p: Promise<unknown>) => {
  try {
    await p
  } catch (e) {
    const r = (e as { response: { status: number; data: { detail: unknown } } })
      .response
    return { status: r.status, detail: r.data.detail }
  }
  throw new Error('expected rejection')
}

beforeEach(() => {
  resetReticleMock()
  setReticleMockNow(() => new Date(NOW))
})
afterEach(async () => {
  resetReticleMock()
  await i18n.changeLanguage('zh-CN')
})

describe('D82 补录时间', () => {
  it('站点墙上时间 → 带偏移 ISO；非法时区用 Asia/Taipei', () => {
    expect(siteWallToIso('2026-10-15T10:05', 'Asia/Taipei')).toBe(
      '2026-10-15T10:05:00+08:00'
    )
    expect(siteWallToIso('2026-10-15T10:05', 'Asia/Tokyo')).toBe(
      '2026-10-15T10:05:00+09:00'
    )
    expect(siteWallToIso('2026-10-15T10:05', 'Bad/Zone')).toBe(
      '2026-10-15T10:05:00+08:00'
    )
    expect(siteWallToIso('2026-10-15')).toBeNull()
  })
  it('前端预校验：4:59、5:00 放行，5:01 拦住', () => {
    expect(tooFarInFuture(at('04:59'), NOW)).toBe(false)
    expect(tooFarInFuture(at('05:00'), NOW)).toBe(false)
    expect(tooFarInFuture(at('05:01'), NOW)).toBe(true)
    const v = (s: string) =>
      validateAction('unmount', { backfill_at: `2026-10-15T10:${s}` }, NOW)
    expect(v('04:59')).toEqual({})
    expect(v('05:00')).toEqual({})
    expect(v('05:01')).toHaveProperty('backfill_at')
  })
  it('mock：5:00 放行，5:01 → 422 value_error future_time', async () => {
    const r = await act('r2', 'unmount', { unmounted_at: at('05:00') })
    expect(r.data).toMatchObject({ unmounted_at: '2026-10-15T02:05:00Z' })
    resetReticleMock()
    setReticleMockNow(() => new Date(NOW))
    expect(
      await fail(act('r2', 'unmount', { unmounted_at: at('05:01') }))
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'value_error', ctx: { reason: 'future_time' } }],
    })
    await act('r2', 'unmount', { unmounted_at: at('04:59') })
  })
  it('mock：不带时区 → 422 timezone_required', async () => {
    expect(
      await fail(act('r2', 'unmount', { unmounted_at: '2026-10-15T09:00:00' }))
    ).toMatchObject({ status: 422, detail: [{ type: 'timezone_required' }] })
  })
  it('mock：下机早于上机 409；相等合法', async () => {
    // r2 于 2026-10-14T01:00:00Z 上机
    expect(
      await fail(act('r2', 'unmount', { unmounted_at: '2026-10-14T00:59:59Z' }))
    ).toMatchObject({ status: 409, detail: { code: 'time_out_of_order' } })
    const r = await act('r2', 'unmount', {
      unmounted_at: '2026-10-14T09:00:00+08:00',
    })
    expect(r.data).toMatchObject({ unmounted_at: '2026-10-14T01:00:00Z' })
  })
  it('mock：早于最近一次下机 / 事件 → 409 time_out_of_order', async () => {
    await act('r2', 'unmount', { unmounted_at: '2026-10-15T01:00:00Z' })
    expect(
      await fail(
        act('r2', 'mount', {
          equipment_id: 'e1',
          mounted_at: '2026-10-15T00:59:00Z',
        })
      )
    ).toMatchObject({ status: 409, detail: { code: 'time_out_of_order' } })
    const m = await act('r2', 'mount', {
      equipment_id: 'e1',
      mounted_at: '2026-10-15T01:00:00Z',
    })
    expect(m.data).toMatchObject({ mounted_at: '2026-10-15T01:00:00Z' })
    expect(
      await fail(
        act('r2', 'incident', {
          kind: 'drop',
          occurred_at: '2026-10-15T00:30:00Z',
        })
      )
    ).toMatchObject({ status: 409, detail: { code: 'time_out_of_order' } })
  })
  it('顺序 D81：422 先于 404 / 409', async () => {
    expect(
      await fail(act('nope', 'unmount', { unmounted_at: at('09:00') }))
    ).toMatchObject({ status: 422 })
    expect(
      await fail(act('r7', 'incident', { kind: 'drop', occurred_at: 'x' }))
    ).toMatchObject({ status: 422 })
    expect(
      await fail(act('nope', 'unmount', { unmounted_at: at('01:00') }))
    ).toMatchObject({ status: 404 })
  })
  it.each(['zh-CN', 'en', 'ja'])('%s：三种错误都有文案', async (lg) => {
    await i18n.changeLanguage(lg)
    const err = (status: number, detail: unknown) =>
      ({
        isAxiosError: true,
        response: { status, data: { detail } },
      }) as never
    const { AxiosError, AxiosHeaders } = await import('axios')
    const mk = (status: number, detail: unknown) => {
      const e = new AxiosError('x')
      e.response = {
        status,
        data: { detail },
        statusText: '',
        headers: {},
        config: { headers: new AxiosHeaders() },
      }
      return e
    }
    void err
    expect(
      reticleErrorMessage(
        mk(422, [{ type: 'value_error', ctx: { reason: 'future_time' } }])
      )
    ).toBe(t('mes.reticle.err.futureTime'))
    expect(
      reticleErrorMessage(
        mk(422, [{ type: 'time_in_future', loc: ['body', 'x'] }])
      )
    ).not.toBe(t('mes.reticle.err.futureTime')) // 旧码不再识别
    expect(
      reticleErrorMessage(
        mk(422, [{ type: 'timezone_required', loc: ['body', 'x'] }])
      )
    ).toBe(t('mes.err.code.timezone_required'))
    expect(
      reticleErrorMessage(mk(409, { code: 'time_out_of_order' }), 'mount')
    ).toBe(t('mes.reticle.code.time_out_of_order'))
  })
})

describe('登记异常顺带下机（后端口径）', () => {
  it('带 occurred_at：用它作为下机时间', async () => {
    // r2 于 2026-10-14T01:00:00Z 上机
    const r = await act('r2', 'incident', {
      kind: 'drop',
      occurred_at: '2026-10-15T09:30:00+08:00',
    })
    expect(r.reticle).toMatchObject({
      status_code: 'on_hold',
      equipment_id: null,
    })
    const m = (await mockReticleApi.history('r2')).mounts.find(
      (x) => x.mounted_at === '2026-10-14T01:00:00Z'
    )
    expect(m).toMatchObject({ unmounted_at: '2026-10-15T01:30:00Z' })
  })
  it('不带 occurred_at：下机时间为当前时间', async () => {
    await act('r2', 'incident', { kind: 'other' })
    const m = (await mockReticleApi.history('r2')).mounts.find(
      (x) => x.mounted_at === '2026-10-14T01:00:00Z'
    )
    expect(m).toMatchObject({ unmounted_at: '2026-10-15T02:00:00Z' })
  })
  it('occurred_at 早于当前上机 → 409，整笔不入库也不下机', async () => {
    const before = await mockReticleApi.get('r2')
    const hb = await mockReticleApi.history('r2')
    expect(
      await fail(
        act('r2', 'incident', {
          kind: 'drop',
          occurred_at: '2026-10-14T00:59:00Z',
        })
      )
    ).toMatchObject({ status: 409, detail: { code: 'time_out_of_order' } })
    expect(await mockReticleApi.get('r2')).toEqual(before)
    expect(await mockReticleApi.history('r2')).toEqual(hb)
  })
})

describe('incident 早于最近一次 usage（D82 补充）', () => {
  it('409 time_out_of_order，整笔回滚；mount / unmount 不比 usage', async () => {
    // r2：上机 10-14T01:00Z，usage 10-14T03:00Z
    const before = await mockReticleApi.get('r2')
    const hb = await mockReticleApi.history('r2')
    expect(
      await fail(
        act('r2', 'incident', {
          kind: 'drop',
          occurred_at: '2026-10-14T02:00:00Z',
        })
      )
    ).toMatchObject({ status: 409, detail: { code: 'time_out_of_order' } })
    expect(await mockReticleApi.get('r2')).toEqual(before)
    expect(await mockReticleApi.history('r2')).toEqual(hb)
    // 正好等于 usage 时间合法
    await act('r2', 'incident', {
      kind: 'drop',
      occurred_at: '2026-10-14T03:00:00Z',
    })
    // unmount 早于 usage 但晚于上机：合法
    resetReticleMock()
    setReticleMockNow(() => new Date(NOW))
    const u = await act('r2', 'unmount', {
      unmounted_at: '2026-10-14T02:00:00Z',
    })
    expect(u.data).toMatchObject({ unmounted_at: '2026-10-14T02:00:00Z' })
  })
})

describe('D80：mount / unmount / incident 必填 key，重放返回原响应', () => {
  it('缺 key 422；同 key 重放原响应且不重复写', async () => {
    for (const [id, a, body] of [
      ['r1', 'mount', { equipment_id: 'e9' }],
      ['r2', 'unmount', {}],
      ['r6', 'incident', { kind: 'drop' }],
    ] as const) {
      expect(await fail(mockReticleApi.act(id, a, { ...body }))).toMatchObject({
        status: 422,
        detail: [{ type: 'missing', loc: ['header', 'Idempotency-Key'] }],
      })
      const k = `rk-${a}`
      const first = await mockReticleApi.act(id, a, { ...body }, k)
      expect(await mockReticleApi.act(id, a, { ...body }, k)).toEqual(first)
    }
    const h = await mockReticleApi.history('r1')
    expect(h.mounts.filter((m) => m.unmounted_at == null)).toHaveLength(1)
  })
})
