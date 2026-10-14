import { beforeEach, describe, expect, it } from 'vitest'
import {
  mockQualHistoryApi as hist,
  mockQualWriteApi as api,
  qualIntent,
  resetQualHistoryMock,
  setQualMockReasons,
  setQualMockUsers,
} from './qual-history'

// B6 40e4342 / D88 对齐
let n = 0
const k = () => `b6-${++n}`
const fail = (p: Promise<unknown>) =>
  p.then(
    () => null,
    (e) => ({ status: e.response.status, detail: e.response.data.detail })
  )
const R = { reason_id: 'R', comment: 'c' }
beforeEach(() => resetQualHistoryMock())

describe('请求体阶段顺序（check_extras）', () => {
  it('缺字段一次全报 missing', async () => {
    expect(
      await fail(api.update('q1', { expires_on: '2027-01-01' }, k()))
    ).toEqual({
      status: 422,
      detail: ['reason_id', 'comment', 'approved_by'].map((f) =>
        expect.objectContaining({ loc: ['body', f], type: 'missing' })
      ),
    })
  })
  it('value_error 一次全报：max_length / invalid_reason / user_not_found；先于 self_approval 和 404', async () => {
    setQualMockReasons(['R'])
    setQualMockUsers(['admin', 'lead'])
    const body = {
      expires_on: '2027-01-01',
      reason_id: 'BAD',
      comment: 'x'.repeat(301),
      approved_by: 'ghost',
    }
    for (const id of ['q1', 'nope'])
      expect(await fail(api.update(id, body, k()))).toEqual({
        status: 422,
        detail: [
          expect.objectContaining({
            loc: ['body', 'comment'],
            ctx: { reason: 'max_length', max_length: 300 },
          }),
          expect.objectContaining({
            loc: ['body', 'reason_id'],
            ctx: { reason: 'invalid_reason' },
          }),
          expect.objectContaining({
            loc: ['body', 'approved_by'],
            ctx: { reason: 'user_not_found' },
          }),
        ],
      })
    // 合法后才判 self_approval（不分大小写）
    expect(
      await fail(
        api.update(
          'nope',
          { expires_on: '2027-01-01', ...R, approved_by: 'ADMIN' },
          k()
        )
      )
    ).toMatchObject({
      status: 422,
      detail: [{ ctx: { reason: 'self_approval' } }],
    })
  })
  it('POST 授予：不要求附加字段；approved_by = 持有人 → holder_approval', async () => {
    const g = {
      username: 'op9',
      operation_id: 'DA',
      equipment_type_id: null,
      certified_on: null,
      expires_on: null,
      is_active: true,
    }
    expect(await api.grant(g, k())).toMatchObject({ username: 'op9' })
    expect(
      await fail(api.grant({ ...g, approved_by: 'OP9' }, k()))
    ).toMatchObject({
      status: 422,
      detail: [{ ctx: { reason: 'holder_approval' } }],
    })
  })
})

describe('D88 带 expires_on 即延期', () => {
  it('意图：带 expires_on（含 null）就是 renew', () => {
    expect(qualIntent({ expires_on: null })).toBe('renew')
    expect(qualIntent({ expires_on: '2026-01-01' })).toBe('renew')
    expect(qualIntent({ certified_on: '2026-01-01' })).toBe('other')
  })
  it('缩短有效期也要批准人，履历记 changed；延长记 renewed', async () => {
    expect(
      await fail(api.update('q1', { expires_on: '2026-10-15', ...R }, k()))
    ).toMatchObject({
      status: 422,
      detail: [{ loc: ['body', 'approved_by'], type: 'missing' }],
    })
    await api.update(
      'q1',
      { expires_on: '2026-10-15', ...R, approved_by: 'lead' },
      k()
    )
    await api.update(
      'q1',
      { expires_on: '2027-10-15', ...R, approved_by: 'lead' },
      k()
    )
    const acts = (await hist.history('q1')).rows.map((r) => r.action)
    expect(acts.slice(0, 2)).toEqual(['renewed', 'changed'])
  })
  it('原来永久改为有期限记 changed', async () => {
    await api.update('q1', { expires_on: null, ...R, approved_by: 'lead' }, k())
    await api.update(
      'q1',
      { expires_on: '2027-01-01', ...R, approved_by: 'lead' },
      k()
    )
    const acts = (await hist.history('q1')).rows.map((r) => r.action)
    expect(acts.slice(0, 2)).toEqual(['changed', 'renewed'])
  })
})

describe('履历接口形状', () => {
  it('404 为 {code:not_found}；行带 comment / reason_id / approved_by、不带 qual_id；offset ctx {min,max}', async () => {
    expect(await fail(hist.history('nope'))).toEqual({
      status: 404,
      detail: expect.objectContaining({ code: 'not_found' }),
    })
    const row = (await hist.history('q1')).rows[0]
    expect(row).not.toHaveProperty('qual_id')
    expect(Object.keys(row)).toEqual(
      expect.arrayContaining(['reason_id', 'comment', 'approved_by'])
    )
    expect(await fail(hist.history('q1', { offset: -1 }))).toMatchObject({
      status: 422,
      detail: [{ loc: ['query', 'offset'], ctx: { min: 0, max: 10 ** 9 } }],
    })
  })
})
