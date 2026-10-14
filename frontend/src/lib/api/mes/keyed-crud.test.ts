import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { http } from '../client'
import { KEYED_ENTITIES, mesApi } from './common'

// QA P2-2：operator_qual 的通用 CRUD 写接口（POST / PATCH / DELETE）都带 Idempotency-Key
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
const key = (c: InternalAxiosRequestConfig) => c.headers?.['Idempotency-Key']

describe('KEYED_ENTITIES', () => {
  it('operator_qual 在清单里', () => {
    expect(KEYED_ENTITIES).toContain('operator_qual')
  })
  it('create / update / remove 传 key 时带头，不传不带', async () => {
    await mesApi.create('operator_qual', { username: 'a' }, 'k1')
    await mesApi.update('operator_qual', 'q1', { is_active: false }, 'k2')
    await mesApi.remove('operator_qual', 'q1', 'k3')
    expect(calls.map((c) => [c.method, key(c)])).toEqual([
      ['post', 'k1'],
      ['patch', 'k2'],
      ['delete', 'k3'],
    ])
    await mesApi.remove('tool', 't1')
    expect(key(calls[3])).toBeUndefined()
  })
})
