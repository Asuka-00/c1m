import { AxiosError, AxiosHeaders } from 'axios'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { MesRow } from '@/lib/api/mes/common'
import { execApi } from '@/lib/api/mes/execution'
import { HistoryTimeline } from './lot-trace'
import { undoErrorLines, undoneInfo } from './transform-undo'

function err(status: number, detail: unknown) {
  const e = new AxiosError(String(status))
  e.response = {
    status,
    data: { detail },
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}

const TRANSFORM: MesRow = {
  id: 'h1',
  action: 'transform',
  at: '2026-10-14T06:00:00Z',
  qty: 2,
  to_status: 'converted',
  details: { transform_id: 'T1', role: 'input', to: ['S1', 'S2'] },
}
const UNDO: MesRow = {
  id: 'h2',
  action: 'transform_undo',
  at: '2026-10-14T07:00:00Z',
  username: 'kai',
  comment: '分错产品',
  details: {
    transform_id: 'T1',
    transform_type: 'dicing',
    children: ['S1', 'S2'],
  },
}

const wrap = (ui: React.ReactNode) => (
  <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>
)

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(() => vi.restoreAllMocks())

describe('F4-02 撤销转换', () => {
  it('已撤销判断：86ca4a1 看 transform_undo 履历，D54 看 undone_at', () => {
    expect(undoneInfo(TRANSFORM, [TRANSFORM])).toBeNull()
    expect(undoneInfo(TRANSFORM, [UNDO, TRANSFORM])).toMatchObject({
      by: 'kai',
      reason: '分错产品',
    })
    expect(
      undoneInfo(
        {
          ...TRANSFORM,
          details: {
            transform_id: 'T1',
            undone_at: '2026-10-14T08:00:00Z',
            undone_by: 'amy',
            undo_reason: 'R1',
          },
        },
        []
      )
    ).toEqual({ at: '2026-10-14T08:00:00Z', by: 'amy', reason: 'R1' })
  })

  it('409 transform_undo_blocked 逐批列出原因', () => {
    expect(
      undoErrorLines(
        err(409, {
          code: 'transform_undo_blocked',
          message: 'x',
          lots: [
            { lot_id: 'a', lot_code: 'S1', reason: 'lot_status' },
            { lot_id: 'b', lot_code: 'S2', reason: 'has_transactions' },
            { lot_id: 'c', lot_code: 'P1', reason: 'parent_status' },
          ],
        })
      )
    ).toEqual([
      'S1：子批已不在等待状态',
      'S2：子批已有后续作业',
      'P1：母批状态已变化',
    ])
    expect(
      undoErrorLines(err(409, { code: 'transform_undo_blocked', lots: [] }))
    ).toEqual([t('mes.tundo.blockedRef')])
    // D54：第二次撤销 409，lots 为空
    expect(
      undoErrorLines(
        err(409, {
          code: 'transform_undo_blocked',
          message: 'transform already undone',
          lots: [],
        })
      )
    ).toEqual([t('mes.tundo.already')])
    expect(undoErrorLines(err(404, 'Record not found'))).toEqual([
      t('mes.tundo.notFound'),
    ])
  })

  it('履历：有权限时未撤销的转换行有撤销入口；提交带原因 / 备注，409 原因显示在对话框', async () => {
    const spy = vi.spyOn(execApi, 'transformUndo').mockRejectedValue(
      err(409, {
        code: 'transform_undo_blocked',
        lots: [{ lot_id: 'a', lot_code: 'S1', reason: 'on_hold' }],
      })
    )
    const s = await render(wrap(<HistoryTimeline rows={[TRANSFORM]} canUndo />))
    await s.getByTestId('open-undo').click()
    await expect
      .element(s.getByTestId('undo-children'))
      .toHaveTextContent('S1、S2')
    await s.getByLabelText(t('mes.exec.comment')).fill(' 分错产品 ')
    await s.getByTestId('do-undo').click()
    await expect
      .element(s.getByTestId('undo-error'))
      .toHaveTextContent('S1：子批处于 Hold')
    expect(spy).toHaveBeenCalledWith('T1', { comment: '分错产品' })
  })

  it('无权限不显示入口；已撤销的转换显示标记、不再给入口；撤销行列出删除的子批', async () => {
    const s = await render(
      wrap(<HistoryTimeline rows={[TRANSFORM]} canUndo={false} />)
    )
    await expect.element(s.getByText('单位转换', { exact: true })).toBeVisible()
    expect(document.querySelector('[data-testid=open-undo]')).toBeNull()
    const s2 = await render(
      wrap(
        <div data-testid='undone'>
          <HistoryTimeline rows={[UNDO, TRANSFORM]} canUndo />
        </div>
      )
    )
    const box = s2.getByTestId('undone')
    await expect
      .element(box.getByTestId('transform-undone'))
      .toHaveTextContent(/已撤销 · .* · kai · 分错产品/)
    expect(
      document.querySelectorAll('[data-testid=undone] [data-testid=open-undo]')
        .length
    ).toBe(0)
    await expect
      .element(box.getByText('撤销切割，删除子批：S1, S2'))
      .toBeVisible()
    await expect
      .element(box.getByText('撤销单位转换', { exact: true }))
      .toBeVisible()
  })

  it('D54 撤销履历：显示撤销时间 / 撤销人 / 撤销原因，载具未恢复时注明', async () => {
    const row: MesRow = {
      ...UNDO,
      details: {
        ...(UNDO.details as object),
        carrier_restored: false,
        undo_reason: 'RC9: 分错产品',
      },
    }
    const s = await render(
      wrap(
        <div data-testid='d54'>
          <HistoryTimeline rows={[row]} canUndo />
        </div>
      )
    )
    const info = s.getByTestId('d54').getByTestId('undo-info')
    await expect
      .element(info)
      .toHaveTextContent(/撤销时间 .+ · 撤销人 kai · 撤销原因 RC9: 分错产品/)
    await expect
      .element(info.getByTestId('undo-carrier'))
      .toHaveTextContent(t('mes.tundo.carrier'))
    // 老形态（无 carrier_restored）不显示载具说明
    await render(wrap(<HistoryTimeline rows={[UNDO]} canUndo />))
    expect(document.querySelectorAll('[data-testid=undo-carrier]').length).toBe(
      1
    )
  })
})
