import { AxiosError, AxiosHeaders } from 'axios'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { mesApi } from '@/lib/api/mes/common'
import { woApi, type StartPlan } from '@/lib/api/mes/planning'
import { SidebarProvider } from '@/components/ui/sidebar'
import LotStartPage from './lot-start'

const PLAN: StartPlan = {
  work_order_id: 'W1',
  wo_status: 'released',
  planned_qty: 50,
  started_qty: 0,
  max_qty: 50,
  remaining: 50,
  lot_size: 25,
  max_lot_size: 25,
  first_step_id: null,
  first_step_seq: null,
  site_id: null,
  lots: [
    { lot_no: 'LOT-1', qty: 25, slots: [], wafer_ids: [] },
    { lot_no: 'LOT-2', qty: 25, slots: [], wafer_ids: [] },
  ],
}

function err422(detail: unknown) {
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

async function show() {
  vi.spyOn(mesApi, 'list').mockImplementation(async (target) =>
    target === 'customer'
      ? ({
          data: [{ id: 'c1', code: 'C1', name: 'Acme' }],
          count: 1,
        } as never)
      : ({ data: [], count: 0 } as never)
  )
  vi.spyOn(woApi, 'plan').mockResolvedValue(PLAN)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms: [],
  })
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => (
        <SidebarProvider>
          <LotStartPage />
        </SidebarProvider>
      ),
    }),
    history: createMemoryHistory({ initialEntries: ['/?wo=W1'] }),
  })
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(() => vi.restoreAllMocks())

const next = (s: Awaited<ReturnType<typeof show>>) =>
  s.getByRole('button', { name: t('mes.start.next') })

describe('开批向导：客户来料（F6）', () => {
  it('客户来料须选客户；选好后请求体带客户字段，自有行只发 ownership', async () => {
    const start = vi
      .spyOn(woApi, 'start')
      .mockResolvedValue({ data: [{ id: 'L1', code: 'LOT-1', qty: 25 }] })
    const s = await show()
    const row0 = s.getByTestId('lot-cust-0')
    await row0.getByLabelText(t('mes.cust.ownership')).selectOptions('customer')
    await expect
      .element(s.getByRole('alert'))
      .toHaveTextContent(t('mes.cust.errCustomer', { n: 1 }))
    await expect.element(next(s)).toBeDisabled()
    await row0.getByText(t('common.select')).click()
    await s.getByRole('option', { name: 'C1 · Acme' }).click()
    await row0.getByLabelText(t('mes.cust.lotNo')).fill('  CL-001 ')
    await expect.element(next(s)).toBeEnabled()
    await next(s).click()
    await expect
      .element(s.getByText('客户来料 · C1 · Acme'))
      .toBeInTheDocument()
    await s
      .getByRole('button', {
        name: t('mes.start.confirmStart', { count: 2, total: 50 }),
      })
      .click()
    await expect.poll(() => start.mock.calls.length).toBe(1)
    const [wo, lots] = start.mock.calls[0]
    expect(wo).toBe('W1')
    expect(lots[0]).toMatchObject({
      ownership: 'customer',
      customer_id: 'c1',
      customer_lot_no: 'CL-001',
    })
    expect(lots[1]).toMatchObject({ ownership: 'own' })
    expect(lots[1]).not.toHaveProperty('customer_id')
    expect(lots[1]).not.toHaveProperty('customer_lot_no')
  })

  it('开批 422：带回第 2 步，错误标在对应批次行的字段下，改了就消失', async () => {
    vi.spyOn(woApi, 'start').mockRejectedValue(
      err422([
        {
          loc: ['body', 'lots', 1, 'customer_id'],
          msg: 'lots.1: customer not found',
          type: 'value_error',
        },
        {
          loc: ['body', 'lots', 0, 'qty'],
          msg: 'lots.0: qty must be 1..25',
          type: 'value_error',
        },
      ])
    )
    const s = await show()
    const row1 = s.getByTestId('lot-cust-1')
    await row1.getByLabelText(t('mes.cust.ownership')).selectOptions('customer')
    await row1.getByText(t('common.select')).click()
    await s.getByRole('option', { name: 'C1 · Acme' }).click()
    await row1.getByLabelText(t('mes.cust.lotNo')).fill('CL-9')
    await next(s).click()
    await s
      .getByRole('button', {
        name: t('mes.start.confirmStart', { count: 2, total: 50 }),
      })
      .click()
    await expect
      .element(s.getByTestId('start-server-errors'))
      .toHaveTextContent(t('mes.start.fe.banner'))
    await expect
      .element(s.getByTestId('lot-cust-1').getByTestId('lot-field-error'))
      .toHaveTextContent(t('mes.start.fe.customerNotFound'))
    await expect.element(s.getByText(t('mes.start.fe.qty'))).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('lots.1:')
    // 改归属后该行客户错误清除
    await row1.getByLabelText(t('mes.cust.ownership')).selectOptions('own')
    await expect
      .poll(
        () =>
          document.querySelectorAll(
            '[data-testid=lot-cust-1] [data-testid=lot-field-error]'
          ).length
      )
      .toBe(0)
  })

  it('D52：客户来料客户批号为空（含只有空格）时前端拦住并标在该行；自有行不受影响', async () => {
    const start = vi.spyOn(woApi, 'start')
    const s = await show()
    const row0 = s.getByTestId('lot-cust-0')
    await row0.getByLabelText(t('mes.cust.ownership')).selectOptions('customer')
    await row0.getByText(t('common.select')).click()
    await s.getByRole('option', { name: 'C1 · Acme' }).click()
    await row0.getByLabelText(t('mes.cust.lotNo')).fill('   ')
    await expect
      .element(row0.getByTestId('lot-field-error'))
      .toHaveTextContent(t('mes.start.fe.customerLotRequired'))
    await expect.element(next(s)).toBeDisabled()
    expect(
      document.querySelectorAll(
        '[data-testid=lot-cust-1] [data-testid=lot-field-error]'
      ).length
    ).toBe(0)
    await row0.getByLabelText(t('mes.cust.lotNo')).fill('CL-1')
    await expect.element(next(s)).toBeEnabled()
    expect(start).not.toHaveBeenCalled()
  })

  it('后端 422 customer_lot_required：三语提示标到对应批次行', async () => {
    vi.spyOn(woApi, 'start').mockRejectedValue(
      err422([
        {
          loc: ['body', 'lots', 0, 'customer_lot_no'],
          msg: 'lots.0: customer lot no. required for customer-owned material',
          type: 'customer_lot_required',
          code: 'customer_lot_required',
        },
      ])
    )
    const s = await show()
    const row0 = s.getByTestId('lot-cust-0')
    await row0.getByLabelText(t('mes.cust.ownership')).selectOptions('customer')
    await row0.getByText(t('common.select')).click()
    await s.getByRole('option', { name: 'C1 · Acme' }).click()
    await row0.getByLabelText(t('mes.cust.lotNo')).fill('X')
    await next(s).click()
    await s
      .getByRole('button', {
        name: t('mes.start.confirmStart', { count: 2, total: 50 }),
      })
      .click()
    await expect
      .element(s.getByTestId('lot-cust-0').getByTestId('lot-field-error'))
      .toHaveTextContent(t('mes.start.fe.customerLotRequired'))
    for (const lng of ['en', 'ja']) {
      await i18n.changeLanguage(lng)
      expect(t('mes.start.fe.customerLotRequired')).not.toContain('mes.start')
    }
  })
})
