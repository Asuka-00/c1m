import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mockMarkingApi, resetMarkingMock } from './marking'
import { mockIdemHeaders } from './mock-utils'
import { mockQualWriteApi as qual, resetQualHistoryMock } from './qual-history'
import { mockReticleApi, resetReticleMock } from './reticle'

// D86：4xx 不进幂等缓存；同 key 重发重新跑完整校验；只有 2xx 回放 / 判 reused
const status = (p: Promise<unknown>) =>
  p.then(
    () => 200,
    (e) =>
      (e as { response: { status: number; data: { detail: unknown } } })
        .response
  )
const code = async (p: Promise<unknown>) => {
  const r = await status(p)
  return typeof r === 'number'
    ? r
    : { s: r.status, c: (r.data.detail as { code?: string })?.code }
}
beforeEach(() => {
  resetQualHistoryMock()
  resetReticleMock()
  resetMarkingMock()
})
afterEach(() => {
  resetQualHistoryMock()
  resetReticleMock()
  resetMarkingMock()
})

describe('D86 资质', () => {
  it('删除同 key 同体重发仍 409 referenced（不是回放）；同 key 换目标不 reused', async () => {
    expect(await code(qual.remove('q1', 'K'))).toEqual({
      s: 409,
      c: 'referenced',
    })
    expect(await code(qual.remove('q1', 'K'))).toEqual({
      s: 409,
      c: 'referenced',
    })
    expect(await code(qual.remove('q2', 'K'))).toEqual({
      s: 409,
      c: 'referenced',
    })
    expect(await code(qual.remove('nope', 'K'))).toEqual({
      s: 404,
      c: undefined,
    })
  })
  it('4xx 后同 key 换体重发重新校验，成功后才缓存', async () => {
    const R = { reason_id: 'R', comment: 'c' }
    expect(
      await code(qual.update('q1', { is_active: false }, 'K2'))
    ).toMatchObject({ s: 422 })
    expect(
      await code(qual.update('q1', { is_active: false, ...R }, 'K2'))
    ).toBe(200)
    // 成功后：同 key 同体回放，换体 reused
    expect(
      await code(qual.update('q1', { is_active: false, ...R }, 'K2'))
    ).toBe(200)
    expect(
      await code(
        qual.update(
          'q1',
          { is_active: false, reason_id: 'X', comment: 'c' },
          'K2'
        )
      )
    ).toEqual({ s: 422, c: 'idempotency_key_reused' })
  })
})

describe('D86 光罩', () => {
  it('409 后状态变化，同 key 同体重发重新校验并成功', async () => {
    expect(
      await code(mockReticleApi.act('r1', 'unmount', {}, 'RK'))
    ).toMatchObject({
      s: 409,
      c: 'invalid_transition',
    })
    await mockReticleApi.act('r1', 'mount', { equipment_id: 'e1' }, 'RM')
    expect(await code(mockReticleApi.act('r1', 'unmount', {}, 'RK'))).toBe(200)
  })
})

describe('D86 打标', () => {
  it('404 后同 key 换目标不 reused', async () => {
    expect(await code(mockMarkingApi.print('nope', {}, 'MK'))).toMatchObject({
      s: 404,
    })
    const r = await mockMarkingApi.create({ lot_id: 'lot1' }, 'MC')
    expect(await code(mockMarkingApi.print(r.id, {}, 'MK'))).toBe(200)
  })
})

const REPLAYED = { 'Idempotent-Replayed': 'true' }
describe('D86 补充二：回放带 Idempotent-Replayed，首次与 4xx 不带', () => {
  it('资质 update', async () => {
    const b = { is_active: false, reason_id: 'R', comment: 'c' }
    const a = await qual.update('q1', b, 'H1')
    expect(mockIdemHeaders()).toEqual({})
    const r = await qual.update('q1', b, 'H1')
    expect(mockIdemHeaders()).toEqual(REPLAYED)
    expect(r).toEqual(a)
    await qual.remove('q1', 'H1').catch(() => {})
    expect(mockIdemHeaders()).toEqual({})
  })
  it('光罩 mount', async () => {
    const a = await mockReticleApi.act(
      'r1',
      'mount',
      { equipment_id: 'e1' },
      'H2'
    )
    expect(mockIdemHeaders()).toEqual({})
    const r = await mockReticleApi.act(
      'r1',
      'mount',
      { equipment_id: 'e1' },
      'H2'
    )
    expect(mockIdemHeaders()).toEqual(REPLAYED)
    expect(r).toEqual(a)
  })
  it('打标 create', async () => {
    const a = await mockMarkingApi.create({ lot_id: 'lot1' }, 'H3')
    expect(mockIdemHeaders()).toEqual({})
    const r = await mockMarkingApi.create({ lot_id: 'lot1' }, 'H3')
    expect(mockIdemHeaders()).toEqual(REPLAYED)
    expect(r).toEqual(a)
  })
})
