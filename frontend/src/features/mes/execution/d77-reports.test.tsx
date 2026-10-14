import {
  AxiosError,
  AxiosHeaders,
  type AxiosAdapter,
  type InternalAxiosRequestConfig,
} from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { http, errorMessage } from '@/lib/api/client'
import {
  execApi,
  mockReportApi,
  mockReportDateCheck,
  reportDates,
} from '@/lib/api/mes/execution'
import { DateRange } from './report-parts'

// D77 补充二：output / oee / yield / oee-trend from>to → 422 value_error ctx.reason=range_inverted；
// 通用 date 筛选非严格 YYYY-MM-DD → 422 pattern，loc=["query", 字段名]
const orig = http.defaults.adapter
let detail: unknown = []
const urls: string[] = []
const params: Record<string, unknown>[] = []
beforeEach(() => {
  urls.length = 0
  http.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
    urls.push(config.url!)
    params.push(config.params)
    const e = new AxiosError('422', 'ERR_BAD_REQUEST', config)
    e.response = {
      status: 422,
      data: { detail },
      statusText: '',
      headers: {},
      config,
    }
    throw e
  }) as AxiosAdapter
})
afterEach(async () => {
  http.defaults.adapter = orig
  await i18n.changeLanguage('zh-CN')
})

const inverted = [
  {
    loc: ['query', 'date_from'],
    type: 'value_error',
    code: 'value_error',
    msg: 'Value error, date_from must not be after date_to',
    ctx: { reason: 'range_inverted' },
  },
]
const p = { date_from: '2026-10-15', date_to: '2026-10-01' }
const reports: [string, () => Promise<unknown>][] = [
  ['output', () => execApi.output(p)],
  ['oee', () => execApi.oee(p)],
  ['yield', () => execApi.yieldReport({ ...p, group: 'operation' })],
  ['oee-trend', () => execApi.oeeTrend(p)],
]

describe('D77 补充二：四个报表 range_inverted', () => {
  it.each(['zh-CN', 'en', 'ja'])('%s', async (lng) => {
    await i18n.changeLanguage(lng)
    detail = inverted
    for (const [name, call] of reports) {
      const e = await call().catch((x) => x)
      expect(e).toBeInstanceOf(AxiosError)
      expect(urls[urls.length - 1]).toBe(`/mes/exec/reports/${name}`)
      expect(errorMessage(e)).toBe(t('mes.err.code.range_inverted'))
    }
  })
  it('date 筛选 422 pattern 有兜底文案（带字段名，不露英文原文）', async () => {
    detail = [
      {
        loc: ['query', 'date_from'],
        type: 'value_error',
        code: 'value_error',
        msg: 'date_from: must be YYYY-MM-DD',
        ctx: { reason: 'pattern', pattern: '^\\d{4}-\\d{2}-\\d{2}$' },
      },
    ]
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      const e = await execApi.output(p).catch((x) => x)
      const m = errorMessage(e)
      expect(m).toBe(t('errors.query.pattern', { field: 'date_from' }))
      expect(m).not.toMatch(/must be/)
    }
  })
  it('报表页日期区间显示后端错误', async () => {
    const e = new AxiosError('422')
    e.response = {
      status: 422,
      data: { detail: inverted },
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
    const s = await render(
      <DateRange
        from='2026-10-01'
        to='2026-10-15'
        setFrom={() => {}}
        setTo={() => {}}
        error={e}
      />
    )
    await expect
      .element(s.getByTestId('report-error'))
      .toHaveTextContent(t('mes.err.code.range_inverted'))
  })
})

describe('D77 补充三：报表日期严格 YYYY-MM-DD', () => {
  it('四个报表发出的 date_from / date_to 都是严格 YYYY-MM-DD', async () => {
    detail = inverted
    params.length = 0
    const q = {
      date_from: '2026-10-01T00:00:00+08:00',
      date_to: '2026-10-15T23:59:59Z',
    }
    await execApi.output(q).catch(() => {})
    await execApi.oee(q).catch(() => {})
    await execApi.yieldReport({ ...q, group: 'operation' }).catch(() => {})
    await execApi.oeeTrend(q).catch(() => {})
    expect(params).toHaveLength(4)
    for (const x of params) {
      expect(x.date_from).toBe('2026-10-01')
      expect(x.date_to).toBe('2026-10-15')
    }
    expect(reportDates({ date_from: '2026-10-01' })).toMatchObject({
      date_from: '2026-10-01',
      date_to: undefined,
    })
  })
  it('mock 顺序：先 422 pattern（loc=query），再 range_inverted', () => {
    const d = (e: AxiosError | null) =>
      (e?.response?.data as { detail: { type: string; loc: unknown[] }[] })
        .detail[0]
    // 带时间且倒置：先报 pattern
    expect(
      d(
        mockReportDateCheck({
          date_from: '2026-10-15T00:00:00Z',
          date_to: '2026-10-01',
        })
      )
    ).toMatchObject({
      type: 'value_error',
      ctx: { reason: 'pattern' },
      loc: ['query', 'date_from'],
    })
    expect(
      d(mockReportDateCheck({ date_from: '2026-10-01', date_to: '2026/10/15' }))
    ).toMatchObject({
      type: 'value_error',
      ctx: { reason: 'pattern' },
      loc: ['query', 'date_to'],
    })
    expect(
      d(mockReportDateCheck({ date_from: '2026-10-15', date_to: '2026-10-01' }))
    ).toMatchObject({ type: 'value_error', ctx: { reason: 'range_inverted' } })
    expect(
      mockReportDateCheck({ date_from: '2026-10-01', date_to: '2026-10-01' })
    ).toBeNull()
  })
})

describe('QA P3：四个报表 mock 接入日期校验', () => {
  it('pattern 先于 range_inverted，合法返回空数据，文案正确', async () => {
    const calls = [
      (q: object) => mockReportApi.output(q),
      (q: object) => mockReportApi.oee(q),
      (q: object) => mockReportApi.yieldReport({ ...q, group: 'operation' }),
      (q: object) => mockReportApi.oeeTrend(q),
    ]
    for (const c of calls) {
      const e1 = await c({
        date_from: '2026-10-15T00:00:00Z',
        date_to: '2026-10-01',
      }).catch((x) => x)
      expect(errorMessage(e1)).toBe(
        t('errors.query.pattern', { field: 'date_from' })
      )
      const e2 = await c({
        date_from: '2026-10-15',
        date_to: '2026-10-01',
      }).catch((x) => x)
      expect(errorMessage(e2)).toBe(t('mes.err.code.range_inverted'))
      await expect(
        c({ date_from: '2026-10-01', date_to: '2026-10-15' })
      ).resolves.toBeTruthy()
    }
  })
})
