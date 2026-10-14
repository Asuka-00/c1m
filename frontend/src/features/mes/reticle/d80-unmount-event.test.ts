import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  D80_KEYED,
  groupHistory,
  mockReticleApi,
  resetReticleMock,
  RETICLE_SOURCES,
  setReticleMockNow,
} from '@/lib/api/mes/reticle'

// be/p3 f9e9dda：下机事件行、source 枚举、inspected_at 校验
const NOW = Date.parse('2026-10-15T02:00:00Z')
let n = 0
const key = () => `d80u-${++n}`

beforeEach(() => {
  resetReticleMock()
  setReticleMockNow(() => new Date(NOW))
})
afterEach(() => resetReticleMock())

describe('D80 f9e9dda 对齐', () => {
  it('14 个写接口全部带 key；source 四值', () => {
    expect(new Set(D80_KEYED).size).toBe(14)
    expect(RETICLE_SOURCES).toEqual(['manual', 'eap', 'simulator', 'system'])
  })

  it('unmount 返回 {data: 上机行, unmount_event: 下机行}，手工不带 duplicate', async () => {
    const r = await mockReticleApi.act('r2', 'unmount', {}, key())
    expect(r.data).toMatchObject({ id: 'm1', event_type: 'mount' })
    expect(r.data.unmounted_at).toBeTruthy()
    expect(r.unmount_event).toMatchObject({
      event_type: 'unmount',
      mount_log_id: 'm1',
      source: 'manual',
      unmounted_at: r.data.unmounted_at,
    })
    expect(r).not.toHaveProperty('duplicate')
  })

  it('履历：type=unmount 的下机行不进挂载页签', () => {
    const h = groupHistory([
      { type: 'mount', id: 'm1', event_type: 'mount' },
      { type: 'unmount', id: 'm1u', event_type: 'unmount', mount_log_id: 'm1' },
      { type: 'mount', id: 'x', event_type: 'unmount' },
    ])
    expect(h.mounts.map((m) => m.id)).toEqual(['m1'])
  })

  it('inspection.inspected_at：无时区 / 超前 5 分钟以上 422（先于状态 409）', async () => {
    const fail = async (v: string) => {
      try {
        await mockReticleApi.act(
          'r2',
          'inspection',
          { kind: 'particle', result: 'pass', inspected_at: v },
          key()
        )
      } catch (e) {
        return (e as { response: { status: number; data: { detail: never } } })
          .response
      }
      throw new Error('expected rejection')
    }
    const a = await fail('2026-10-15T10:00:00')
    expect(a.status).toBe(422)
    expect(a.data.detail[0]).toMatchObject({ code: 'timezone_required' })
    const b = await fail('2026-10-15T02:05:01Z')
    expect(b.status).toBe(422)
    expect(b.data.detail[0]).toMatchObject({
      code: 'value_error',
      ctx: { reason: 'future_time' },
    })
  })
})
