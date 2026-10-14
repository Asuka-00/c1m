import { AxiosError, AxiosHeaders } from 'axios'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { http } from '@/lib/api/client'
import type { BoardRow } from '@/lib/api/mes/equipment'
import type { CheckResult } from '@/lib/api/mes/execution'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ReasonButton } from '@/components/reason-button'
import { enumLabel } from '@/features/mes/common/labels'
import { checkMessage } from '@/features/mes/execution/check-message'
import { QualBadge, QualDialog } from './qual'
import { isWaitQual, qualError } from './qual-rules'

const row = (over: Partial<BoardRow> = {}): BoardRow => ({
  id: 'e1',
  code: 'EAP-DA01',
  name: 'DA01',
  is_active: true,
  state: {
    id: 's',
    code: 'SBY',
    name: 'Standby',
    category: 'SBY',
    color: null,
  },
  next: [],
  workcenter: null,
  workcenter_name: null,
  chambers: [],
  pm: [],
  pm_due: false,
  pm_warn: false,
  down: false,
  qual_state: 'wait_qual',
  qual_task_id: 'task-1',
  ...over,
})
const task = {
  id: 'task-1',
  equipment_id: 'e1',
  sub_unit_id: 'u1',
  sub_unit_label: 'EAP-DA01-BH1',
  pm_plan_label: null,
  requested_at: '2026-10-14T05:58:05Z',
  qual_status: 'open',
}
const axErr = (status: number, detail: unknown) =>
  new AxiosError('x', 'ERR', undefined, undefined, {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: { detail },
  })

const wrap = (el: React.ReactNode) => (
  <QueryClientProvider client={new QueryClient()}>
    <TooltipProvider>{el}</TooltipProvider>
  </QueryClientProvider>
)

afterEach(() => vi.restoreAllMocks())

describe('F5 待 Qual', () => {
  it('取自 qual_state，与 E10 状态无关', () => {
    expect(isWaitQual(row())).toBe(true)
    expect(isWaitQual(row({ qual_state: 'ready' }))).toBe(false)
  })

  it('显示待 Qual 的子单元，悬停为本地时间', async () => {
    const s = await render(wrap(<QualBadge row={row()} task={task} />))
    const b = s.getByTestId('qual-EAP-DA01')
    await expect
      .element(b)
      .toHaveTextContent(t('mes.eqp.qual.waitSub', { unit: 'EAP-DA01-BH1' }))
    await expect
      .element(b)
      .toHaveAttribute(
        'title',
        `${t('mes.eqp.qual.requestedAt')}: ${fmtDateTime(task.requested_at)}`
      )
  })

  it('已放行不显示标记', async () => {
    const s = await render(
      wrap(<QualBadge row={row({ qual_state: 'ready' })} />)
    )
    expect(s.container.textContent).toBe('')
  })

  it('D34：403 只提示无权限，不带字段细节', () => {
    const m = qualError(
      axErr(403, [{ loc: ['body', 'result'], msg: 'secret' }])
    )
    expect(m).toBe(t('mes.eqp.qual.err.forbidden'))
    expect(m).not.toContain('result')
  })

  it('404 任务不存在，409 qual_task_closed 已登记', () => {
    expect(qualError(axErr(404, 'Record not found'))).toBe(
      t('mes.eqp.qual.err.notFound')
    )
    const m = qualError(
      axErr(409, { code: 'qual_task_closed', qual_status: 'passed' })
    )
    expect(m).toBe(
      t('mes.eqp.qual.err.closedAs', {
        status: enumLabel('qual_status', 'passed'),
      })
    )
    expect(m).not.toContain('Qual task already')
    expect(qualError(axErr(409, { code: 'qual_task_closed' }))).toBe(
      t('mes.eqp.qual.err.closed')
    )
  })

  it('登记：请求体只含 result / comment，409 显示本地提示', async () => {
    const post = vi
      .spyOn(http, 'post')
      .mockRejectedValue(axErr(409, { code: 'qual_task_closed' }))
    const s = await render(
      wrap(<QualDialog row={row()} task={task} onClose={() => {}} />)
    )
    await s.getByTestId('qual-submit').click()
    expect(post).toHaveBeenCalledWith('/mes/eqp/qual/task-1/result', {
      result: 'pass',
    })
    await expect
      .element(s.getByRole('alert'))
      .toHaveTextContent(t('mes.eqp.qual.err.closed'))
  })

  it('禁用按钮可键盘聚焦并显示原因', async () => {
    const fn = vi.fn()
    const s = await render(
      wrap(
        <ReasonButton
          label={t('mes.eqp.qual.record')}
          reason={t('mes.eqp.qual.noPermission')}
          testId='qb'
          onClick={fn}
        />
      )
    )
    await expect.element(s.getByTestId('qb')).toBeDisabled()
    await userEvent.tab()
    await expect.element(s.getByTestId('qb-reason')).toHaveFocus()
    await expect
      .element(s.getByRole('tooltip'))
      .toHaveTextContent(t('mes.eqp.qual.noPermission'))
  })

  it('开工拦截 eqp_wait_qual 显示本地文案', () => {
    const r: CheckResult = {
      check_type: 'eqp_wait_qual',
      rule_id: null,
      rule_code: null,
      rule_name: null,
      plan_code: null,
      severity: 'block',
      result: 'block',
      applicable: true,
      message: 'EAP-DA01 is waiting for Qual after PM (WAIT_QUAL)',
      overridable: false,
      data: { equipment: 'EAP-DA01', task_id: 'task-1' },
    }
    const m = checkMessage(r)
    expect(m).toBe(
      t('mes.exec.checkMsg.eqp_wait_qual', { equipment: 'EAP-DA01' })
    )
    expect(m).not.toMatch(/WAIT_QUAL/)
  })
})
