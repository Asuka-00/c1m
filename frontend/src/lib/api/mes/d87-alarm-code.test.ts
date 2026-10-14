import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { http } from '../client'
import { KEYED_ENTITIES, mesApi } from './common'
import { createKeyedCrudMock } from './keyed-crud-mock'
import { mockIdemHeaders } from './mock-utils'

// D87 补充二：alarm_code 通用 CRUD 新建 / 编辑 / 删除带 key（后端 B8 强制）
const m = createKeyedCrudMock('alarm_code', [{ id: 'a1', alid: '1001' }])
const st = (f: () => unknown) => {
  try {
    f()
    return 200
  } catch (e) {
    const r = (e as { response: { status: number; data: { detail: unknown } } })
      .response
    return { s: r.status, d: r.data.detail }
  }
}
beforeEach(() => m.reset())

describe('D87 补充二 alarm_code', () => {
  it('在 KEYED_ENTITIES', () => {
    expect(KEYED_ENTITIES).toContain('alarm_code')
  })
  it.each([
    ['create', () => m.create({ alid: '2' })],
    ['update', () => m.update('nope', { alid: '2' })],
    ['remove', () => m.remove('nope')],
  ])('%s 缺 key → 422 missing（先于 404）', (_, f) => {
    expect(st(f)).toEqual({
      s: 422,
      d: [
        expect.objectContaining({
          loc: ['header', 'Idempotency-Key'],
          type: 'missing',
        }),
      ],
    })
  })
  it('同 key 换请求体 → 422 ctx.reason=reused；同体回放带 Idempotent-Replayed', () => {
    const a = m.create({ alid: '2001' }, 'K')
    expect(mockIdemHeaders()).toEqual({})
    expect(m.create({ alid: '2001' }, 'K')).toEqual(a)
    expect(mockIdemHeaders()).toEqual({ 'Idempotent-Replayed': 'true' })
    expect(st(() => m.create({ alid: '2002' }, 'K'))).toEqual({
      s: 422,
      d: [expect.objectContaining({ ctx: { reason: 'reused' } })],
    })
    expect(st(() => m.update('a1', { alid: 'x' }, 'K'))).toMatchObject({
      s: 422,
    })
  })
  it('删除成功后同 key 回放不 404；4xx 不缓存', () => {
    expect(st(() => m.remove('zz', 'D'))).toMatchObject({ s: 404 })
    expect(st(() => m.remove('a1', 'D'))).toBe(200)
    expect(st(() => m.remove('a1', 'D'))).toBe(200)
    expect(mockIdemHeaders()).toEqual({ 'Idempotent-Replayed': 'true' })
  })
})

describe('http：alarm_code 写接口带 Idempotency-Key', () => {
  const calls: InternalAxiosRequestConfig[] = []
  const orig = http.defaults.adapter
  beforeEach(() => {
    calls.length = 0
    http.defaults.adapter = (async (config) => {
      calls.push(config)
      return { data: {}, status: 200, statusText: '', headers: {}, config }
    }) as AxiosAdapter
  })
  afterEach(() => {
    http.defaults.adapter = orig
  })
  it('POST / PATCH / DELETE（后端 get_entity 把 - 归一为 _，等价 /mes/alarm_code/{rid}）', async () => {
    await mesApi.create('alarm_code', { alid: '1' }, 'k1')
    await mesApi.update('alarm_code', 'a1', { alid: '2' }, 'k2')
    await mesApi.remove('alarm_code', 'a1', 'k3')
    expect(
      calls.map((c) => [c.method, c.url, c.headers?.['Idempotency-Key']])
    ).toEqual([
      ['post', '/mes/alarm-code', 'k1'],
      ['patch', '/mes/alarm-code/a1', 'k2'],
      ['delete', '/mes/alarm-code/a1', 'k3'],
    ])
  })
})
