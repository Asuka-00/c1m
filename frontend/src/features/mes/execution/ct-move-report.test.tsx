import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { http } from '@/lib/api/client'
import { ctMoveApi, ctMoveMock } from '@/lib/api/mes/ct-move'
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
