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
import { genealogyRows } from './trace-rows'

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
          customer_name: 'Acme',
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
    await expect.element(res).toHaveTextContent('客户来料 · C1 · Acme')
    // 下游子批没有名称：只显示编码
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

  it('FE-OF61-1：按 9c5e568 样例（正向子批只带 customer / customer_name、无 lot_id）显示客户名称', async () => {
    const { s } = await show({
      kind: 'customer_lot',
      target: { customer_lot_no: 'CL-T' },
      lots: [
        {
          lot_no: 'FX0001',
          lot_status: 'moved_in',
          customer_lot_no: 'CL-T',
          ownership: 'customer',
          customer_id: '3aa7707d-81da-480c-9915-0a8ade41db74',
          customer: 'C1',
          customer_name: 'Cust 1',
          forward: {
            lots: [
              {
                code: 'FX0001.01',
                relation: 'split',
                customer_lot_no: 'CL-T',
                customer: 'C1',
                customer_name: 'Cust 1',
              },
            ],
          },
        },
        {
          lot_no: 'FX0001.01',
          lot_status: 'moved_in',
          customer_lot_no: 'CL-T',
          ownership: 'customer',
          customer_id: '3aa7707d-81da-480c-9915-0a8ade41db74',
          customer: 'C1',
          customer_name: 'Cust 1',
          forward: { lots: [] },
        },
      ],
    } as unknown as TraceResult)
    await s.getByRole('combobox', { name: t('mes.traceq.kind') }).click()
    await s
      .getByRole('option', { name: t('mes.traceq.k.customer_lot') })
      .click()
    await s.getByLabelText(t('mes.traceq.code')).fill('CL-T')
    await userEvent.click(s.getByTestId('trace-search'))
    const res = s.getByTestId('customer-lot-result')
    await expect.element(res).toHaveTextContent('FX0001.01')
    const labels = () =>
      Array.from(
        document.querySelectorAll(
          '[data-testid=customer-lot-result] [data-testid=ownership-label]'
        ),
        (x) => x.textContent
      )
    // 匹配批次表 2 行 + 两个批次块头部各 1 + 正向子批 1 行，全部为「客户来料 · C1 · Cust 1」，没有误显示为自有
    await expect.poll(() => labels().length).toBe(5)
    expect(new Set(labels())).toEqual(new Set(['客户来料 · C1 · Cust 1']))
  })

  it('D54：转换谱系的批次带 transform_id，追溯表显示转换记录列', async () => {
    const { s } = await show({
      kind: 'lot',
      target: { id: 'L1', code: 'LOT-T', ownership: 'own', customer: null },
      backward: empty,
      forward: {
        lots: [
          {
            id: 'C1',
            code: 'LOT-T-1',
            relation: 'transform',
            qty: 10,
            via: 'LOT-T',
            level: 1,
            at: null,
            transform_id: '1234abcd-0000-4000-8000-000000000001',
          },
          {
            id: 'C2',
            code: 'LOT-T-2',
            relation: 'split',
            qty: 5,
            via: 'LOT-T',
            level: 1,
            at: null,
            transform_id: null,
          },
        ],
      },
    } as never)
    await s.getByLabelText(t('mes.traceq.code')).fill('LOT-T')
    await userEvent.click(s.getByTestId('trace-search'))
    await expect
      .element(s.getByText(t('mes.traceq.c.transform_id')).first())
      .toBeVisible()
    const cell = s.getByTitle('1234abcd-0000-4000-8000-000000000001')
    await expect.element(cell).toHaveTextContent('1234abcd')
  })

  it('D60：undone=true 的转换节点显示已撤销及撤销信息，缺失字段不显示', async () => {
    const { s } = await show({
      kind: 'lot',
      target: { id: 'L1', code: 'LOT-U', ownership: 'own', customer: null },
      backward: empty,
      forward: {
        lots: [
          {
            id: 'C1',
            code: 'LOT-U-1',
            relation: 'transform',
            qty: 10,
            via: 'LOT-U',
            level: 1,
            at: null,
            transform_id: 'aaaabbbb-0000-4000-8000-000000000001',
            undone: true,
            undone_at: '2026-10-14T08:00:00Z',
            undone_by: 'kai',
            undo_reason: 'map 选错了',
          },
          {
            id: 'C2',
            code: 'LOT-U-2',
            relation: 'transform',
            qty: 5,
            via: 'LOT-U',
            level: 1,
            at: null,
            undone: true,
          },
        ],
      },
    } as never)
    await s.getByLabelText(t('mes.traceq.code')).fill('LOT-U')
    await userEvent.click(s.getByTestId('trace-search'))
    await expect
      .poll(
        () => document.querySelectorAll('[data-testid=trace-undone]').length
      )
      .toBe(2)
    const info = document.querySelectorAll('[data-testid=trace-undone-info]')
    expect(info.length).toBe(1)
    expect(info[0].textContent).toMatch(/· kai · map 选错了$/)
  })

  it('a46d232：已撤销节点（id=null）不做跳转、不计入谱系数量', async () => {
    const { s } = await show({
      kind: 'lot',
      target: { id: 'L2', code: 'LOT-V', ownership: 'own', customer: null },
      backward: empty,
      forward: {
        lots: [
          {
            id: 'C9',
            code: 'LOT-V-1',
            relation: 'split',
            qty: 3,
            via: 'LOT-V',
            level: 1,
            at: null,
            undone: false,
          },
          {
            id: null,
            code: 'LOT-V-X',
            relation: 'transform',
            qty: null,
            via: 'LOT-V',
            level: 1,
            at: null,
            undone: true,
            undone_at: '2026-10-14T08:00:00Z',
            undone_by: 'kai',
            undo_reason: null,
          },
        ],
      },
    } as never)
    await s.getByLabelText(t('mes.traceq.code')).fill('LOT-V')
    await userEvent.click(s.getByTestId('trace-search'))
    await expect.element(s.getByText('LOT-V-X')).toBeVisible()
    expect(s.getByText('LOT-V-X').element().closest('a')).toBeNull()
    expect(s.getByText('LOT-V-1').element().closest('a')).not.toBeNull()
    await expect
      .element(s.getByText(`${t('mes.traceq.outLots')} (1)`))
      .toBeVisible()
    expect(
      genealogyRows([{ undone: true }, { undone: false }, {}])
    ).toHaveLength(2)
  })
})

describe('P3-F4 追溯码（kind=trace_code）', () => {
  it('显示打标记录和晶圆', async () => {
    const { s } = await show({
      kind: 'trace_code',
      target: { code: 'LOT-A001', id: 'lot1' },
      marking: {
        trace_code: '26420001',
        content: 'FS3201 / 2642 26420001',
        latest_inspection_status: 'pass',
      },
      wafers: [{ wafer: 'LOT-A001-W01', slot: 1 }],
    })
    await userEvent.fill(
      s.getByLabelText(t('mes.traceq.code')).element(),
      'LOT-A001'
    )
    await s.getByTestId('trace-search').click()
    await expect.element(s.getByText('26420001', { exact: true })).toBeVisible()
    await expect.element(s.getByText('LOT-A001-W01')).toBeVisible()
    await expect
      .element(s.getByText(t('mes.marking.insp.pass'), { exact: true }))
      .toBeVisible()
  })
  it('追溯码格式不符前端逐条提示，不发请求', async () => {
    const { s, spy } = await show({ kind: 'lot', target: {} })
    await s.getByLabelText(t('mes.traceq.kind')).click()
    await s.getByRole('option', { name: t('mes.traceq.k.trace_code') }).click()
    await userEvent.fill(
      s.getByLabelText(t('mes.traceq.code')).element(),
      'a'.repeat(33)
    )
    await s.getByTestId('trace-search').click()
    const err = s.getByTestId('trace-code-err')
    await expect
      .element(err)
      .toHaveTextContent(t('mes.marking.err.trace_max_length', { n: 32 }))
    await expect
      .element(err)
      .toHaveTextContent(t('mes.marking.err.trace_pattern'))
    expect(spy).not.toHaveBeenCalled()
  })
})
