import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/lib/api/client'
import { KEYED_ENTITIES } from '@/lib/api/mes/common'
import { mockIdemHeaders } from '@/lib/api/mes/mock-utils'
import {
  httpReticleApi,
  mockReticleApi,
  resetReticleMock,
} from '@/lib/api/mes/reticle'

// D87 补充一：光罩主数据通用 CRUD 新建 / 编辑 / 删除必带 Idempotency-Key
const no = undefined as unknown as string
const st = (p: Promise<unknown>) =>
  p.then(
    () => 200,
    (e) => ({ s: e.response.status, d: e.response.data.detail })
  )
const MISSING = {
  s: 422,
  d: [
    expect.objectContaining({
      loc: ['header', 'Idempotency-Key'],
      type: 'missing',
    }),
  ],
}
beforeEach(() => resetReticleMock())
afterEach(() => vi.restoreAllMocks())

describe('D87 补充一 光罩主数据带 key', () => {
  it('reticle 在 KEYED_ENTITIES', () => {
    expect(KEYED_ENTITIES).toContain('reticle')
  })
  it('mock 缺 key → 422 missing（先于请求体 / 404）', async () => {
    expect(await st(mockReticleApi.save(null, { code: '' }, no))).toEqual(
      MISSING
    )
    expect(await st(mockReticleApi.save('nope', { layer: 'X' }, no))).toEqual(
      MISSING
    )
    expect(await st(mockReticleApi.remove('nope', no))).toEqual(MISSING)
  })
  it('带 key：成功后同 key 同体回放（带 Idempotent-Replayed），换体 reused；4xx 不缓存', async () => {
    const a = await mockReticleApi.save(null, { code: 'RT-K1' }, 'K1')
    expect(mockIdemHeaders()).toEqual({})
    const b = await mockReticleApi.save(null, { code: 'RT-K1' }, 'K1')
    expect(mockIdemHeaders()).toEqual({ 'Idempotent-Replayed': 'true' })
    expect(b).toEqual(a)
    expect(
      await st(mockReticleApi.save(null, { code: 'RT-K2' }, 'K1'))
    ).toMatchObject({
      s: 422,
      d: { code: 'idempotency_key_reused' },
    })
    // r2 有履历 → 409；同 key 重发仍 409（不是回放）
    expect(await st(mockReticleApi.remove('r2', 'D1'))).toMatchObject({
      s: 409,
    })
    expect(await st(mockReticleApi.remove('r2', 'D1'))).toMatchObject({
      s: 409,
    })
  })
  it('http 新建 / 编辑带 Idempotency-Key', async () => {
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
    const patch = vi.spyOn(http, 'patch').mockResolvedValue({ data: {} })
    await httpReticleApi.save(null, { code: 'X' }, 'k1')
    await httpReticleApi.save('r1', { layer: 'M2' }, 'k2')
    expect(post).toHaveBeenCalledWith(
      '/mes/reticle',
      { code: 'X' },
      { headers: { 'Idempotency-Key': 'k1' } }
    )
    expect(patch).toHaveBeenCalledWith(
      '/mes/reticle/r1',
      { layer: 'M2' },
      { headers: { 'Idempotency-Key': 'k2' } }
    )
  })
})
