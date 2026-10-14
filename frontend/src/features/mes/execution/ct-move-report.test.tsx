import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { http } from '@/lib/api/client'
import {
  CT_MOVE_MAX_DAYS,
  ctMoveApi,
  ctMoveMock,
  normalizeReport,
  rangeDays,
  rangeProblem,
} from '@/lib/api/mes/ct-move'
import { mesErrorMessage } from '@/features/mes/common/required'
import { CtMoveChart } from './ct-move-report'

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(() => vi.restoreAllMocks())

describe('P3 CT / Move 报表（前端假设接口）', () => {
  it('示例数据：按日连续、按工序过滤、小数为字符串', () => {
    const r = ctMoveMock({ date_from: '2026-10-01', date_to: '2026-10-07' })
    expect(r.trend.map((x) => x.day)).toHaveLength(7)
    expect(r.trend[0].day).toBe('2026-10-01')
    expect(typeof r.trend[0].ct_avg_hours).toBe('string')
    expect(r.by_operation).toHaveLength(5)
    const one = ctMoveMock({
      date_from: '2026-10-01',
      date_to: '2026-10-01',
      operation_id: 'op-wb',
    })
    expect(one.by_operation.map((x) => x.operation)).toEqual(['WB'])
    expect(one.mock).toBe(true)
  })

  it('接口 404（未上线）时回退示例数据；其他错误照常抛出', async () => {
    const e404 = new AxiosError('404')
    e404.response = {
      status: 404,
      data: {},
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
    const get = vi.spyOn(http, 'get').mockRejectedValueOnce(e404)
    const r = await ctMoveApi.report({
      date_from: '2026-10-01',
      date_to: '2026-10-02',
    })
    expect(r.mock).toBe(true)
    expect(get.mock.calls[0][0]).toBe('/mes/exec/reports/ct-move')
    const e500 = new AxiosError('500')
    get.mockRejectedValueOnce(e500)
    await expect(
      ctMoveApi.report({ date_from: '2026-10-01', date_to: '2026-10-02' })
    ).rejects.toBe(e500)
  })

  it('趋势图渲染，空数据显示无结果', async () => {
    const r = ctMoveMock({ date_from: '2026-10-01', date_to: '2026-10-03' })
    const s = await render(<CtMoveChart rows={r.trend} />)
    await expect.element(s.getByTestId('ct-move-chart')).toBeInTheDocument()
    const s2 = await render(<CtMoveChart rows={[]} />)
    await expect.element(s2.getByText(t('common.noResults'))).toBeVisible()
  })
})

describe('P3 CT / Move（D62 + D63 + D64）', () => {
  it('跨度预校验：92 天可查，93 天超限，倒序无效', () => {
    expect(rangeDays('2026-01-01', '2026-04-02')).toBe(92)
    expect(rangeProblem('2026-01-01', '2026-04-02')).toBeNull()
    expect(rangeProblem('2026-01-01', '2026-04-03')).toBe('too_large')
    expect(rangeProblem('2026-02-01', '2026-01-01')).toBe('invalid')
    expect(CT_MOVE_MAX_DAYS).toBe(92)
  })

  it('422 date_range_too_large 三语本地化', async () => {
    const e = new AxiosError('422')
    e.response = {
      status: 422,
      data: { detail: { code: 'date_range_too_large' } },
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
    for (const lg of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lg)
      const m = mesErrorMessage(e, undefined)
      expect(m).toContain('92')
      expect(m).not.toContain('date_range_too_large')
    }
  })

  it('422 date_range_too_large 列表形式（架构：所有 422 detail 为列表）也显示文案', async () => {
    const mk = (detail: unknown) => {
      const e = new AxiosError('422')
      e.response = {
        status: 422,
        data: { detail },
        statusText: '',
        headers: {},
        config: { headers: new AxiosHeaders() },
      }
      return e
    }
    const list = mk([
      {
        loc: ['query', 'date_to'],
        msg: 'date range too large (max 92 days)',
        type: 'date_range_too_large',
        code: 'date_range_too_large',
      },
    ])
    const typeOnly = mk([
      { loc: ['query', 'date_to'], msg: 'x', type: 'date_range_too_large' },
    ])
    for (const lg of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lg)
      const want = t('mes.err.code.date_range_too_large')
      expect(mesErrorMessage(list, undefined)).toBe(want)
      expect(mesErrorMessage(typeOnly, undefined)).toBe(want)
      expect(
        mesErrorMessage(mk({ code: 'date_range_too_large' }), undefined)
      ).toBe(want)
    }
    await i18n.changeLanguage('zh-CN')
  })

  it('空数据补齐：计数 0、时长 null', () => {
    const r = normalizeReport({
      date_from: '2026-10-01',
      date_to: '2026-10-01',
      timezone: 'Asia/Tokyo',
      trend: [{ day: '2026-10-01' } as never],
      by_operation: [],
      total: {} as never,
    })
    expect(r.trend[0]).toMatchObject({
      moves: 0,
      move_qty: '0',
      rework_moves: 0,
      ct_avg_hours: null,
      hold_hours: null,
    })
    expect(r.total.hold_hours).toBeNull()
    expect(r.timezone).toBe('Asia/Tokyo')
  })

  it('示例数据含空日，图表 null CT 正常渲染', async () => {
    const r = ctMoveMock({ date_from: '2026-10-01', date_to: '2026-10-07' })
    expect(r.trend[5]).toMatchObject({ moves: 0, ct_avg_hours: null })
    expect(r.trend[0].rework_moves).toBe(1)
    const s = await render(<CtMoveChart rows={r.trend} />)
    await expect.element(s.getByTestId('ct-move-chart')).toBeInTheDocument()
  })
})
