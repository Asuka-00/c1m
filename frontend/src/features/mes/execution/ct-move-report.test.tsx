import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { http } from '@/lib/api/client'
import {
  CT_MOVE_MAX_DAYS,
  ctMoveApi,
  ctMoveMock,
  mockCtMoveReport,
  normalizeReport,
  rangeDays,
  rangeProblem,
} from '@/lib/api/mes/ct-move'
import { mesErrorMessage } from '@/features/mes/common/required'
import { ctMoveErrorMessage } from './ct-move-errors'
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

  it('真实接口 GET /mes/exec/reports/ct-move；404 不再回退示例数据', async () => {
    const e404 = new AxiosError('404')
    e404.response = {
      status: 404,
      data: { detail: 'operation not found' },
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
    const get = vi.spyOn(http, 'get').mockRejectedValueOnce(e404)
    await expect(
      ctMoveApi.report({
        date_from: '2026-10-01',
        date_to: '2026-10-02',
        operation_id: 'x',
      })
    ).rejects.toBe(e404)
    expect(get.mock.calls[0][0]).toBe('/mes/exec/reports/ct-move')
    expect(get.mock.calls[0][1]).toEqual({
      params: {
        date_from: '2026-10-01',
        date_to: '2026-10-02',
        operation_id: 'x',
        product_id: undefined,
      },
    })
    for (const lg of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lg)
      expect(ctMoveErrorMessage(e404)).toBe(t('mes.ctMove.notFound'))
    }
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
    expect(rangeProblem('2026-02-01', '2026-01-01')).toBe('inverted')
    expect(rangeProblem('2026-02-01', '2026-02-01')).toBeNull()
    expect(rangeProblem('2026-02-01', 'x')).toBe('invalid')
    expect(CT_MOVE_MAX_DAYS).toBe(92)
  })

  it('422 date_range_too_large 三语本地化', async () => {
    const e = new AxiosError('422')
    e.response = {
      status: 422,
      data: { detail: { code: 'date_range_too_large', max_days: 92 } },
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
        ctx: { max_days: 92 },
      },
    ])
    const typeOnly = mk([
      {
        loc: ['query', 'date_to'],
        msg: 'x',
        type: 'date_range_too_large',
        ctx: { max_days: 92 },
      },
    ])
    const noMax = mk([
      { loc: ['query', 'date_to'], msg: 'x', code: 'date_range_too_large' },
    ])
    for (const lg of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lg)
      const want = t('mes.err.code.date_range_too_large', { max_days: 92 })
      expect(want).toContain('92')
      expect(mesErrorMessage(list, undefined)).toBe(want)
      expect(mesErrorMessage(typeOnly, undefined)).toBe(want)
      const nolimit = t('mes.err.code.date_range_too_large_nolimit')
      expect(mesErrorMessage(noMax, undefined)).toBe(nolimit)
      expect(
        mesErrorMessage(mk({ code: 'date_range_too_large' }), undefined)
      ).toBe(nolimit)
      expect(mesErrorMessage(noMax, undefined)).not.toContain('{{')
    }
    await i18n.changeLanguage('zh-CN')
  })

  it('页面前端校验超 92 天时按 CT_MOVE_MAX_DAYS 插值', () => {
    expect(
      t('mes.err.code.date_range_too_large', { max_days: CT_MOVE_MAX_DAYS })
    ).toContain(String(CT_MOVE_MAX_DAYS))
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

describe('P3-B5 真实接口对齐（be/p3 2c19bb3）', () => {
  it('normalizeReport 补 on_hold_lots / on_hold_qty；时长 null 保持 null', () => {
    const r = normalizeReport({
      date_from: '2026-10-01',
      date_to: '2026-10-01',
      timezone: 'Asia/Tokyo',
      trend: [],
      by_operation: [
        {
          operation_id: 'o',
          operation: 'OP',
          operation_name: null,
          moves: 0,
        } as never,
      ],
      total: {} as never,
    })
    expect(r.by_operation[0]).toMatchObject({
      on_hold_lots: 0,
      on_hold_qty: '0',
      ct_p50_hours: null,
      ct_p90_hours: null,
    })
    expect(r.total.ct_avg_hours).toBeNull()
    expect(r.timezone).toBe('Asia/Tokyo')
  })
  it('mock：倒置 422 range_inverted、93 天 422 date_range_too_large、未知工序 404', () => {
    const st = (f: () => unknown) => {
      try {
        f()
      } catch (e) {
        return (e as AxiosError).response
      }
      throw new Error('expected error')
    }
    expect(
      st(() =>
        mockCtMoveReport({ date_from: '2026-10-02', date_to: '2026-10-01' })
      )
    ).toMatchObject({
      status: 422,
      data: { detail: [{ ctx: { reason: 'range_inverted' } }] },
    })
    expect(
      st(() =>
        mockCtMoveReport({ date_from: '2026-01-01', date_to: '2026-04-03' })
      )
    ).toMatchObject({
      status: 422,
      data: {
        detail: [{ type: 'date_range_too_large', ctx: { max_days: 92 } }],
      },
    })
    expect(
      st(() =>
        mockCtMoveReport({
          date_from: '2026-10-01',
          date_to: '2026-10-01',
          operation_id: 'nope',
        })
      )
    ).toMatchObject({ status: 404 })
    const ok = mockCtMoveReport({
      date_from: '2026-10-01',
      date_to: '2026-10-01',
    })
    expect(ok.by_operation[1]).toMatchObject({
      on_hold_lots: 1,
      on_hold_qty: '25',
    })
  })
  it.each(['zh-CN', 'en', 'ja'])(
    '%s：range_inverted / too_large 文案',
    async (lg) => {
      await i18n.changeLanguage(lg)
      for (const k of ['range_inverted', 'date_range_too_large'])
        expect(i18n.exists(`mes.err.code.${k}`)).toBe(true)
      expect(i18n.exists('mes.ctMove.notFound')).toBe(true)
      expect(i18n.exists('mes.ctMove.onHold')).toBe(true)
    }
  )
})

describe('CT/Move 跨度边界（含两端 ≤92 天，to − from ≤ 91）', () => {
  it('91 / 92 天可查，93 天前端拦住，mock 422', () => {
    expect(rangeDays('2026-01-01', '2026-04-01')).toBe(91)
    expect(rangeProblem('2026-01-01', '2026-04-01')).toBeNull()
    expect(rangeDays('2026-01-01', '2026-04-02')).toBe(92)
    expect(rangeProblem('2026-01-01', '2026-04-02')).toBeNull()
    expect(rangeDays('2026-01-01', '2026-04-03')).toBe(93)
    expect(rangeProblem('2026-01-01', '2026-04-03')).toBe('too_large')
    expect(
      mockCtMoveReport({ date_from: '2026-01-01', date_to: '2026-04-02' }).trend
    ).toHaveLength(92)
    expect(() =>
      mockCtMoveReport({ date_from: '2026-01-01', date_to: '2026-04-03' })
    ).toThrow()
  })
  it('无数据的天：计数 0，时长 null', () => {
    const r = mockCtMoveReport({
      date_from: '2026-10-01',
      date_to: '2026-10-06',
    })
    expect(r.trend[5]).toMatchObject({
      moves: 0,
      move_qty: '0',
      rework_moves: 0,
      rework_move_qty: '0',
      ct_avg_hours: null,
      hold_hours: null,
    })
  })
})

describe('ct-move 404 分开提示（be/p3 59fb7c5）', () => {
  it.each(['zh-CN', 'en', 'ja'])(
    '%s：operation_not_found / product_not_found',
    async (lg) => {
      await i18n.changeLanguage(lg)
      const get = (f: () => unknown) => {
        try {
          f()
        } catch (e) {
          return e
        }
        throw new Error('expected')
      }
      const op = get(() =>
        mockCtMoveReport({
          date_from: '2026-10-01',
          date_to: '2026-10-01',
          operation_id: 'nope',
        })
      )
      const pr = get(() =>
        mockCtMoveReport({
          date_from: '2026-10-01',
          date_to: '2026-10-01',
          product_id: 'missing-1',
        })
      )
      expect(ctMoveErrorMessage(op)).toBe(t('mes.ctMove.operationNotFound'))
      expect(ctMoveErrorMessage(pr)).toBe(t('mes.ctMove.productNotFound'))
    }
  )
})
