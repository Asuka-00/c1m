import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  mockQualExpiryScan,
  mockQualHistoryApi as hist,
  mockQualWriteApi as api,
  mockTrackInQualCheck,
  qualMockEvents,
  qualMockWarnDays,
  resetQualHistoryMock,
  setQualMockNow,
  setQualMockPerms,
  setQualMockWarnDays,
  QUAL_CHECK_TYPE,
} from './qual-history'

// 台北 2026-10-15 10:00
const NOW = new Date('2026-10-15T02:00:00Z')
let n = 0
const k = () => `qk-${++n}`
const fail = async (p: Promise<unknown>) => {
  try {
    await p
  } catch (e) {
    const r = (e as { response: { status: number; data: { detail: unknown } } })
      .response
    return { status: r.status, detail: r.data.detail as never }
  }
  throw new Error('expected rejection')
}
beforeEach(() => {
  resetQualHistoryMock()
  setQualMockNow(() => NOW)
})
afterEach(() => resetQualHistoryMock())

const R = { reason_id: 'RQ1', comment: '培训复核通过' }

describe('B6 资质履历 mock', () => {
  it('授予 / 延期 / 变更 / 停用 / 恢复各留一条履历并发 operator_qual.* 事件', async () => {
    const g = await api.grant(
      {
        username: 'op9',
        operation_id: 'DA',
        equipment_type_id: null,
        certified_on: '2026-10-15',
        expires_on: '2027-10-14',
        is_active: true,
      },
      k()
    )
    await api.update(
      g.id,
      { expires_on: '2028-10-14', ...R, approved_by: 'lead1' },
      k()
    )
    await api.update(g.id, { equipment_type_id: 'DA-X' }, k())
    await api.update(g.id, { is_active: false, ...R }, k())
    await api.update(g.id, { is_active: true }, k())
    const { rows } = await hist.history(g.id)
    expect(rows.map((r) => r.action)).toEqual([
      'reactivated',
      'deactivated',
      'changed',
      'renewed',
      'granted',
    ])
    const renew = rows[3]
    expect(renew).toMatchObject({
      before: { expires_on: '2027-10-14' },
      after: { expires_on: '2028-10-14' },
      reason_id: 'RQ1',
      comment: '培训复核通过',
      approved_by: 'lead1',
    })
    expect(renew.at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/)
    expect(qualMockEvents().map((e) => e.type)).toEqual([
      'operator_qual.granted',
      'operator_qual.renewed',
      'operator_qual.changed',
      'operator_qual.deactivated',
    ])
    expect(qualMockEvents()[1]).toMatchObject({
      expires_on_before: '2027-10-14',
      expires_on: '2028-10-14',
      approved_by: 'lead1',
      comment: '培训复核通过',
    })
  })

  it('停用 / 延期缺 reason_id、comment，延期缺 approved_by → 422 missing，先于 404', async () => {
    const cases: [object, string][] = [
      [{ is_active: false, comment: 'x' }, 'reason_id'],
      [{ is_active: false, reason_id: 'R' }, 'comment'],
      [{ is_active: false, reason_id: 'R', comment: '  ' }, 'comment'],
      [
        { expires_on: '2030-01-01', comment: 'x', approved_by: 'l' },
        'reason_id',
      ],
      [
        { expires_on: '2030-01-01', reason_id: 'R', approved_by: 'l' },
        'comment',
      ],
      [{ expires_on: '2030-01-01', ...R }, 'approved_by'],
    ]
    for (const [body, field] of cases)
      for (const id of ['q1', 'nope'])
        expect(await fail(api.update(id, body, k()))).toMatchObject({
          status: 422,
          detail: [{ type: 'missing', loc: ['body', field] }],
        })
    expect(await fail(api.update('nope', { ...R }, k()))).toMatchObject({
      status: 404,
    })
  })

  it('D85 self_approval（=请求人）先于 404；holder_approval（=持有人）404 之后、409 之前', async () => {
    const selfBody = { expires_on: '2030-01-01', ...R, approved_by: 'admin' }
    for (const id of ['q1', 'nope'])
      expect(await fail(api.update(id, selfBody, k()))).toMatchObject({
        status: 422,
        detail: [
          {
            type: 'value_error',
            loc: ['body', 'approved_by'],
            ctx: { reason: 'self_approval' },
          },
        ],
      })
    const body = { expires_on: '2030-01-01', ...R, approved_by: 'op1' }
    expect(await fail(api.update('nope', body, k()))).toMatchObject({
      status: 404,
    })
    expect(await fail(api.update('q1', body, k()))).toMatchObject({
      status: 422,
      detail: [
        {
          type: 'value_error',
          loc: ['body', 'approved_by'],
          ctx: { reason: 'holder_approval' },
        },
      ],
    })
    // holder_approval 先于 409：停用后再以持有人批准停用
    await api.update('q1', { is_active: false, ...R }, k())
    expect(
      await fail(
        api.update('q1', { is_active: false, ...R, approved_by: 'op1' }, k())
      )
    ).toMatchObject({
      status: 422,
      detail: [{ ctx: { reason: 'holder_approval' } }],
    })
    expect(
      await fail(api.update('q1', { is_active: false, ...R }, k()))
    ).toMatchObject({ status: 409, detail: { code: 'invalid_transition' } })
    expect(
      await fail(
        api.update(
          'q1',
          { is_active: false, reason_id: 'R', comment: 'あ'.repeat(301) },
          k()
        )
      )
    ).toMatchObject({
      status: 422,
      detail: [{ ctx: { reason: 'max_length', max_length: 300 } }],
    })
  })

  it('D81：403 → 缺 key 422 → 请求体 422 → 重放 / reused', async () => {
    setQualMockPerms(['mes.exec:read'])
    expect(
      await fail(api.update('q1', {}, undefined as unknown as string))
    ).toMatchObject({ status: 403 })
    setQualMockPerms(['mes.exec:read', 'mes.exec:write'])
    expect(
      await fail(
        api.update('q1', { is_active: false }, undefined as unknown as string)
      )
    ).toMatchObject({
      status: 422,
      detail: [{ loc: ['header', 'Idempotency-Key'], type: 'missing' }],
    })
    // @ts-expect-error key 必填
    void api.update('q1', {}).catch(() => {})
    // @ts-expect-error key 必填
    void api.grant({} as never).catch(() => {})
    const a = await api.update('q1', { is_active: false, ...R }, 'same')
    const b = await api.update('q1', { is_active: false, ...R }, 'same')
    expect(b).toEqual(a)
    expect(
      (await hist.history('q1')).rows.filter((r) => r.action === 'deactivated')
    ).toHaveLength(1)
    expect(
      await fail(
        api.update(
          'q1',
          { is_active: false, reason_id: 'X', comment: 'y' },
          'same'
        )
      )
    ).toMatchObject({ status: 422, detail: { code: 'idempotency_key_reused' } })
  })

  it('履历接口：403 > 404；倒序；limit 默认 50、最大 200；offset', async () => {
    setQualMockPerms([])
    expect(await fail(hist.history('nope'))).toMatchObject({ status: 403 })
    setQualMockPerms(null)
    expect(await fail(hist.history('nope'))).toMatchObject({ status: 404 })
    for (let i = 0; i < 3; i++) {
      setQualMockNow(() => new Date(NOW.getTime() + i * 1000))
      await api.update('q1', { equipment_type_id: `T${i}` }, k())
    }
    const all = (await hist.history('q1')).rows
    expect(all.map((r) => r.at)).toEqual(
      [...all.map((r) => r.at)].sort().reverse()
    )
    expect(
      (await hist.history('q1', { limit: 1, offset: 1 })).rows[0].after
    ).toEqual({
      equipment_type_id: 'T1',
    })
    expect(await fail(hist.history('q1', { limit: 201 }))).toMatchObject({
      status: 422,
      detail: [{ loc: ['query', 'limit'], ctx: { max: 200 } }],
    })
  })

  it('有履历的资质删除 409 referenced', async () => {
    expect(await fail(api.remove('q1'))).toMatchObject({
      status: 409,
      detail: { code: 'referenced', tables: ['mes_operator_qual_log'] },
    })
  })

  it('过期不自动停用：扫描写 expired 履历 + 事件，去重；进站 409 check_blocked 带 expires_on', async () => {
    // q2 2026-10-10 已过期；q1 2026-10-20 未过期
    expect(mockQualExpiryScan()).toBe(1)
    expect(mockQualExpiryScan()).toBe(0)
    const h = (await hist.history('q2')).rows
    expect(h[0]).toMatchObject({
      action: 'expired',
      username: 'system',
      after: { expires_on: '2026-10-10' },
    })
    expect(qualMockEvents().map((e) => e.type)).toEqual([
      'operator_qual.expired',
    ])
    const e = mockTrackInQualCheck('op2', 'WB', 'WB-ASM')!
    expect(e.response!.status).toBe(409)
    const d = (e.response!.data as { detail: never }).detail as {
      code: string
      overridable: boolean
      results: { check_type: string; overridable: boolean; ctx: object }[]
    }
    expect(d).toMatchObject({ code: 'check_blocked', overridable: false })
    expect(d.results[0]).toMatchObject({
      check_type: QUAL_CHECK_TYPE,
      overridable: false,
      ctx: { expires_on: '2026-10-10', qual_id: 'q2' },
    })
    // 当天有效（站点时区）
    setQualMockNow(() => new Date('2026-10-20T15:59:59Z'))
    expect(mockTrackInQualCheck('op1', 'DA')).toBeNull()
    setQualMockNow(() => new Date('2026-10-20T16:00:00Z'))
    expect(mockTrackInQualCheck('op1', 'DA')).not.toBeNull()
  })

  it('预警天数单一来源：warn_days 1–365 整数，否则 30', () => {
    expect(qualMockWarnDays()).toBe(30)
    setQualMockWarnDays(14)
    expect(qualMockWarnDays()).toBe(14)
    setQualMockWarnDays(0)
    expect(qualMockWarnDays()).toBe(30)
    setQualMockWarnDays(400)
    expect(qualMockWarnDays()).toBe(30)
  })
})
