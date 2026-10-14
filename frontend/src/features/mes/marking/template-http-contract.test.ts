import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { http } from '@/lib/api/client'
import {
  COMMENT_MAX,
  httpMarkingApi as api,
  mockMarkingApi,
  resetMarkingMock,
} from '@/lib/api/mes/marking'

// 后端补充确认：模板接口方法 / 路径 / Idempotency-Key / 成功状态码；comment 上限
const calls: InternalAxiosRequestConfig[] = []
let status = 200
const orig = http.defaults.adapter
beforeEach(() => {
  calls.length = 0
  resetMarkingMock()
  http.defaults.adapter = (async (config) => {
    calls.push(config)
    return {
      data: { id: 't9', version: 2, lines: [] },
      status,
      statusText: '',
      headers: {},
      config,
    }
  }) as AxiosAdapter
})
afterEach(() => {
  http.defaults.adapter = orig
  resetMarkingMock()
})
const last = () => calls[calls.length - 1]
const idem = (c: InternalAxiosRequestConfig) =>
  c.headers?.['Idempotency-Key'] ?? null

const input = {
  code: 'X',
  product_id: 'p3',
  customer_id: 'c1',
  lines: ['{product_code}'],
  date_code_basis: 'marking' as const,
  uses_bin: false,
}

describe('模板 HTTP 契约', () => {
  it('创建 POST /mes/marking-template，201，带 key', async () => {
    status = 201
    await api.createTemplate(input, 'k1')
    expect(last().method).toBe('post')
    expect(last().url).toBe('/mes/marking-template')
    expect(idem(last())).toBe('k1')
  })
  it('新版本 POST /mes/marking-template/{id}/versions，201，带 key', async () => {
    status = 201
    await api.newVersion('t1', 'k2')
    expect(last().method).toBe('post')
    expect(last().url).toBe('/mes/marking-template/t1/versions')
    expect(idem(last())).toBe('k2')
  })
  it('编辑 PATCH /mes/marking-template/{id}，200，带 key', async () => {
    status = 200
    await api.updateTemplate('t1', { lines: ['x'] }, 'k3')
    expect(last().method).toBe('patch')
    expect(last().url).toBe('/mes/marking-template/t1')
    expect(idem(last())).toBe('k3')
  })
  it('审批 POST /mes/marking-template/{id}/approve，200，带 key', async () => {
    status = 200
    await api.approve('t1', 'k4')
    expect(last().method).toBe('post')
    expect(last().url).toBe('/mes/marking-template/t1/approve')
    expect(idem(last())).toBe('k4')
  })
  it('预览 / 校验 POST，只读不带 key', async () => {
    status = 200
    await api.templatePreview({ template_id: 't1' })
    expect(last().method).toBe('post')
    expect(last().url).toBe('/mes/marking-template/preview')
    expect(idem(last())).toBeNull()
    await api.templateValidate({ template_id: 't1' })
    expect(last().method).toBe('post')
    expect(last().url).toBe('/mes/marking-template/validate')
    expect(idem(last())).toBeNull()
  })
})

describe('mock 预览 / 校验与 comment 上限', () => {
  it('预览 / 校验不要 key', async () => {
    const p = await mockMarkingApi.templatePreview({ lines: ['{lot_id}'] })
    expect(p.lines).toEqual(['LOT-SAMPLE'])
    expect(
      await mockMarkingApi.templateValidate({ lines: ['{model}'] })
    ).toEqual({ valid: false, unknown_placeholders: ['model'] })
    expect(
      (await mockMarkingApi.templateValidate({ template_id: 't1' })).valid
    ).toBe(true)
  })
  it('检验 comment 超长 422 value_error {reason:max_length, max_length:300}', async () => {
    expect(COMMENT_MAX).toBe(300)
    const r = await mockMarkingApi.create({ lot_id: 'lot1' }, 'c1')
    await mockMarkingApi.print(r.id, {}, 'p1')
    const e = await mockMarkingApi
      .inspect(
        r.id,
        {
          result: 'pass',
          read_code: r.trace_code,
          comment: 'あ'.repeat(301),
        },
        'i1'
      )
      .catch((x) => x)
    expect(e.response.status).toBe(422)
    expect(e.response.data.detail[0]).toMatchObject({
      type: 'value_error',
      ctx: { reason: 'max_length', max_length: 300 },
    })
    // 300 个码点不超
    await mockMarkingApi.inspect(
      r.id,
      { result: 'pass', read_code: r.trace_code, comment: '😀'.repeat(300) },
      'i2'
    )
  })
})
