import {
  AxiosError,
  AxiosHeaders,
  type AxiosAdapter,
  type InternalAxiosRequestConfig,
} from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { setSiteTz } from '@/lib/site-tz'
import { mapListParams } from '@/features/mes/map/map-list-params'
import { errorMessage, http } from './client'
import { ctMoveApi, mockCtMoveReport } from './mes/ct-move'
import { execApi } from './mes/execution'
import { shiftLogApi } from './mes/shift-log'
import {
  STRICT_DATE_FIELDS,
  mockListQueryDateCheck,
  mockQueryDateCheck,
  normalizeListQuery,
  offsetDatetime,
  strictDate,
} from './query-dates'

const orig = http.defaults.adapter
const calls: InternalAxiosRequestConfig[] = []
beforeEach(() => {
  setSiteTz('Asia/Taipei')
  calls.length = 0
  http.defaults.adapter = (async (config) => {
    calls.push(config)
    return {
      data: { data: [] },
      status: 200,
      statusText: '',
      headers: {},
      config,
    }
  }) as AxiosAdapter
})
afterEach(async () => {
  http.defaults.adapter = orig
  await i18n.changeLanguage('zh-CN')
})
const OFF = /(Z|[+-]\d{2}:\d{2})$/
const ent = {
  code: 'work_order',
  fields: [
    { name: 'due_date', column: 'due_date', type: 'date' },
    { name: 'planned_start', column: 'planned_start', type: 'date' },
    { name: 'released_at', column: 'released_at', type: 'datetime' },
  ],
} as never

describe('a72b85b：datetime 带偏移', () => {
  it('offsetDatetime：日期 → 站点 0 点；_to → 次日 0 点；墙上时间补偏移；已带偏移原样', () => {
    expect(offsetDatetime('2026-10-15')).toBe('2026-10-15T00:00:00+08:00')
    expect(offsetDatetime('2026-10-15', true)).toBe('2026-10-16T00:00:00+08:00')
    expect(offsetDatetime('2026-10-15T08:30')).toBe('2026-10-15T08:30:00+08:00')
    expect(offsetDatetime('2026-10-15T00:00:00Z')).toBe('2026-10-15T00:00:00Z')
  })
  it('通用列表：datetime 等值与 _from/_to 带偏移，date 严格 YYYY-MM-DD', () => {
    const q = normalizeListQuery(ent, {
      released_at: '2026-10-15T08:00',
      released_at_from: '2026-10-01',
      released_at_to: '2026-10-15',
      due_date_from: '2026-10-01T00:00:00+08:00',
      due_date: '2026-10-20',
      q: 'x',
    })
    expect(q).toEqual({
      released_at: '2026-10-15T08:00:00+08:00',
      released_at_from: '2026-10-01T00:00:00+08:00',
      released_at_to: '2026-10-16T00:00:00+08:00',
      due_date_from: '2026-10-01',
      due_date: '2026-10-20',
      q: 'x',
    })
  })
  it('holds 的 date_from / date_to 带偏移', async () => {
    await execApi.holds({
      held_at_from: '2026-10-01',
      held_at_to: '2026-10-15T23:59:59.999999+08:00',
    })
    expect(calls[0].params.date_from).toMatch(OFF)
    expect(calls[0].params.date_to).toMatch(OFF)
  })
  it('map imported_from / imported_to 带偏移', () => {
    const p = mapListParams({
      from: '2026-10-01',
      to: '2026-10-15',
      q: '',
      substrate: '',
      page: 1,
    } as never)
    expect(p.imported_from).toMatch(OFF)
    expect(p.imported_to).toMatch(OFF)
  })
})

describe('a72b85b：date 严格 YYYY-MM-DD', () => {
  it('11 个字段清单', () => {
    expect(STRICT_DATE_FIELDS).toHaveLength(11)
    expect(strictDate('2026-10-15T00:00:00Z')).toBe('2026-10-15')
  })
  it('shift-logs、ct-move 只发 YYYY-MM-DD', async () => {
    await shiftLogApi.list({
      date_from: '2026-10-01T00:00:00+08:00',
      date_to: '2026-10-15',
    })
    expect(calls[0].params).toEqual({
      date_from: '2026-10-01',
      date_to: '2026-10-15',
    })
    await ctMoveApi
      .report({
        date_from: '2026-10-01T00:00:00Z',
        date_to: '2026-10-02T00:00:00Z',
      } as never)
      .catch(() => {})
    expect(calls[1].params.date_from).toBe('2026-10-01')
    expect(calls[1].params.date_to).toBe('2026-10-02')
  })
})

describe('a72b85b mock 校验与文案', () => {
  const first = (e: AxiosError | null) =>
    (
      e!.response!.data as {
        detail: { type: string; ctx?: object; loc: unknown[] }[]
      }
    ).detail[0]
  it('date 不合格式 value_error reason=pattern；datetime 无时区 timezone_required；无法解析 pattern', () => {
    const k = { d: 'date', t: 'datetime' } as const
    expect(first(mockQueryDateCheck({ d: '2026/10/01' }, k))).toMatchObject({
      type: 'value_error',
      ctx: { reason: 'pattern' },
      loc: ['query', 'd'],
    })
    expect(
      first(mockQueryDateCheck({ d: '2026-10-01T00:00:00Z' }, k))
    ).toMatchObject({
      ctx: { reason: 'pattern' },
    })
    const tz = first(mockQueryDateCheck({ t: '2026-10-01T00:00' }, k))
    expect(tz).toMatchObject({ type: 'timezone_required', loc: ['query', 't'] })
    expect(tz.ctx).toBeUndefined()
    expect(first(mockQueryDateCheck({ t: '2026-10-01' }, k)).type).toBe(
      'timezone_required'
    )
    expect(first(mockQueryDateCheck({ t: 'yesterday' }, k))).toMatchObject({
      type: 'value_error',
      ctx: { reason: 'pattern' },
    })
    expect(
      mockQueryDateCheck({ d: '2026-10-01', t: '2026-10-01T00:00:00+08:00' }, k)
    ).toBeNull()
  })
  it('ct-move mock：先 pattern 后 range_inverted', () => {
    let e: unknown
    try {
      mockCtMoveReport({
        date_from: '2026-10-15T00:00:00Z',
        date_to: '2026-10-01',
      } as never)
    } catch (x) {
      e = x
    }
    expect(errorMessage(e)).toBe(
      t('errors.query.pattern', { field: 'date_from' })
    )
  })
  it.each(['zh-CN', 'en', 'ja'])(
    '%s timezone_required 兜底文案',
    async (lng) => {
      await i18n.changeLanguage(lng)
      const e = new AxiosError('422')
      e.response = {
        status: 422,
        data: {
          detail: [
            {
              loc: ['query', 'created_at_from'],
              type: 'timezone_required',
              code: 'timezone_required',
              msg: 'x',
            },
          ],
        },
        statusText: '',
        headers: {},
        config: { headers: new AxiosHeaders() },
      }
      expect(errorMessage(e)).toBe(t('mes.err.code.timezone_required'))
    }
  )
})

describe('D85：datetime 等值与 _from/_to 同一套校验', () => {
  it('前端等值带偏移；mock 等值与范围报同样的错', () => {
    expect(
      normalizeListQuery(ent, { released_at: '2026-10-15' }).released_at
    ).toBe('2026-10-15T00:00:00+08:00')
    for (const k of ['released_at', 'released_at_from', 'released_at_to']) {
      const tz = mockListQueryDateCheck(ent, { [k]: '2026-10-15T08:00' })
      expect(
        (tz!.response!.data as { detail: { type: string; loc: unknown[] }[] })
          .detail[0]
      ).toMatchObject({ type: 'timezone_required', loc: ['query', k] })
      const bad = mockListQueryDateCheck(ent, { [k]: 'nope' })
      expect(
        (bad!.response!.data as { detail: { ctx: object }[] }).detail[0].ctx
      ).toEqual({ reason: 'pattern' })
      expect(
        mockListQueryDateCheck(ent, { [k]: '2026-10-15T08:00:00+08:00' })
      ).toBeNull()
    }
    expect(
      mockListQueryDateCheck(ent, { due_date: '2026-10-15T00:00:00Z', q: 'x' })
    ).not.toBeNull()
  })
})
