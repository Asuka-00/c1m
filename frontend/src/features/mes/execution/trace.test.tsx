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
import { userEvent } from 'vitest/browser'
import { execApi, type TraceResult } from '@/lib/api/mes/execution'
import { SidebarProvider } from '@/components/ui/sidebar'
import TracePage from './trace'

const empty = { lots: [], steps: [], materials: [] }

async function show(res: TraceResult) {
  const spy = vi.spyOn(execApi, 'trace').mockResolvedValue(res)
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => (
        <SidebarProvider>
          <TracePage />
        </SidebarProvider>
      ),
    }),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  const s = await render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  return { s, spy }
}

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(() => vi.restoreAllMocks())

describe('F6 追溯显示客户批号和归属', () => {
  it('按客户批号查询：kind=customer_lot，列出批次和客户信息（F6-03）', async () => {
    const { s, spy } = await show({
      kind: 'customer_lot',
      target: { customer_lot_no: 'cl-001' },
      lots: [
        {
          lot_id: 'L1',
          lot_no: 'LOT-A',
          lot_status: 'waiting',
          customer_lot_no: 'CL-001',
          ownership: 'customer',
          customer_id: 'c1',
          customer: 'C1',
          backward: empty,
          forward: {
            lots: [
              {
                id: 'L2',
                code: 'LOT-A.1',
                customer_lot_no: 'CL-001',
                ownership: 'customer',
                customer: 'C1',
                relation: 'split',
                qty: 5,
                level: 1,
              },
            ],
          },
        },
      ],
    })
    await s.getByRole('combobox', { name: t('mes.traceq.kind') }).click()
    await s
      .getByRole('option', { name: t('mes.traceq.k.customer_lot') })
      .click()
    await s.getByLabelText(t('mes.traceq.code')).fill(' cl-001 ')
    await userEvent.click(s.getByTestId('trace-search'))
    await expect.poll(() => spy.mock.calls.length).toBe(1)
    expect(spy.mock.calls[0]).toEqual(['customer_lot', 'cl-001'])
    const res = s.getByTestId('customer-lot-result')
    await expect.element(res).toHaveTextContent('LOT-A')
    await expect.element(res).toHaveTextContent('LOT-A.1')
    await expect.element(res).toHaveTextContent('客户来料 · C1')
    await expect.element(res).toHaveTextContent('CL-001')
    await expect
      .element(s.getByTestId('lot-customer-lot').first())
      .toHaveTextContent(`${t('mes.cust.lotNo')}: CL-001`)
  })

  it('按批次追溯：头部显示归属，自有批次不显示客户批号', async () => {
    const { s } = await show({
      kind: 'lot',
      target: {
        id: 'L1',
        code: 'LOT-B',
        customer_lot_no: null,
        ownership: 'own',
        customer: null,
      },
      backward: empty,
      forward: { lots: [] },
    })
    await s.getByLabelText(t('mes.traceq.code')).fill('LOT-B')
    await userEvent.click(s.getByTestId('trace-search'))
    await expect
      .element(s.getByTestId('lot-ownership'))
      .toHaveTextContent('自有')
    expect(document.querySelector('[data-testid=lot-customer-lot]')).toBeNull()
  })

  it('F4：从子批反查到母晶圆和 die 坐标（来源位置表）', async () => {
    const { s } = await show({
      kind: 'lot',
      target: { id: 'S1', code: 'S1', ownership: 'own' },
      backward: {
        ...empty,
        lots: [
          { id: 'W', code: 'LOT-W', relation: 'transform', qty: 22, level: 1 },
        ],
        origins: [
          {
            child_lot: 'S1',
            child_seq: 1,
            child_unit: null,
            parent_lot: 'LOT-W',
            parent_wafer: 'WF001-01',
            die_row: 3,
            die_col: 7,
            qty: 1,
          },
        ],
      },
      forward: { lots: [] },
    })
    await s.getByLabelText(t('mes.traceq.code')).fill('S1')
    await userEvent.click(s.getByTestId('trace-search'))
    await expect
      .element(s.getByText(t('mes.traceq.origins'), { exact: false }))
      .toBeInTheDocument()
    await expect.element(s.getByText('WF001-01')).toBeInTheDocument()
    await expect
      .element(s.getByText(t('mes.enum.genealogy_relation.transform')))
      .toBeInTheDocument()
  })
})
