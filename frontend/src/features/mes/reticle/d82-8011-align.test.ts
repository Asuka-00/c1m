import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  mockReticleApi,
  resetReticleMock,
  setReticleMockNow,
  setReticleMockPerms,
} from '@/lib/api/mes/reticle'
import { MES_PERM } from '@/features/mes/common/mes-perm'

// 386c4e0 对齐：未挂载下机 409、incident 早于上机 409 带 latest_event_at、403 先于缺 key 422
const NOW = Date.parse('2026-10-15T02:00:00Z')
let n = 0
const key = () => `al-${++n}`
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
afterEach(() => resetReticleMock())

describe('386c4e0 mock 对齐', () => {
  it('未挂载时下机 409 invalid_transition', async () => {
    expect(
      await fail(mockReticleApi.act('r1', 'unmount', {}, key()))
    ).toMatchObject({ status: 409, detail: { code: 'invalid_transition' } })
  })
  it('incident occurred_at 早于 mounted_at → 409 time_out_of_order，latest_event_at=上机时间，整笔回滚', async () => {
    const before = await mockReticleApi.get('r2')
    expect(
      await fail(
        mockReticleApi.act(
          'r2',
          'incident',
          { kind: 'drop', occurred_at: '2026-10-14T00:30:00Z' },
          key()
        )
      )
    ).toMatchObject({
      status: 409,
      detail: {
        code: 'time_out_of_order',
        field: 'occurred_at',
        latest_event_at: '2026-10-14T01:00:00Z',
      },
    })
    const after = await mockReticleApi.get('r2')
    expect(after.status_code).toBe(before.status_code)
    const h = await mockReticleApi.history('r2')
    expect(h.mounts[0].unmounted_at).toBeNull()
  })
  it('运行时 403 先于缺 key 422；有权限时缺 key 422', async () => {
    setReticleMockPerms([MES_PERM.reticleRead])
    expect(
      await fail(mockReticleApi.act('r2', 'unmount', {}, undefined))
    ).toMatchObject({ status: 403 })
    setReticleMockPerms([MES_PERM.reticleWrite])
    expect(
      await fail(mockReticleApi.act('r1', 'scrap', {}, undefined))
    ).toMatchObject({ status: 403 })
    expect(
      await fail(mockReticleApi.act('r2', 'unmount', {}, undefined))
    ).toMatchObject({
      status: 422,
      detail: [{ loc: ['header', 'Idempotency-Key'], type: 'missing' }],
    })
  })
})

describe('latest_event_at 取 detail 顶层（D82 补充三）', () => {
  it('mock 放顶层；解析只读顶层', async () => {
    const { latestEventAt, reticleErrorMessage } =
      await import('./reticle-rules')
    const { fmtDateTime, t } = await import('@/i18n')
    const e = await mockReticleApi
      .act(
        'r2',
        'incident',
        { kind: 'drop', occurred_at: '2026-10-14T00:30:00Z' },
        key()
      )
      .catch((x) => x)
    const d = e.response.data.detail
    expect(d.latest_event_at).toBe('2026-10-14T01:00:00Z')
    expect(d.ctx?.latest_event_at).toBeUndefined()
    expect(latestEventAt(e)).toBe('2026-10-14T01:00:00Z')
    expect(reticleErrorMessage(e, 'incident')).toBe(
      t('mes.reticle.err.timeOutOfOrderAt', {
        at: fmtDateTime('2026-10-14T01:00:00Z'),
      })
    )
    e.response.data.detail = {
      code: 'time_out_of_order',
      ctx: { latest_event_at: '2026-10-14T02:00:00Z' },
    }
    // D82 补充三：只按顶层取，ctx 里的不读
    expect(latestEventAt(e)).toBeNull()
    e.response.data.detail = { code: 'time_out_of_order' }
    expect(latestEventAt(e)).toBeNull()
    expect(reticleErrorMessage(e, 'incident')).toBe(
      t('mes.reticle.code.time_out_of_order')
    )
  })
})
