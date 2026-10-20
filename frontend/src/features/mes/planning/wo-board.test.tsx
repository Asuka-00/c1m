import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { t } from '@/i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { woApi, type WoBoardRow } from '@/lib/api/mes/planning'
import { SidebarProvider } from '@/components/ui/sidebar'
import WoBoard from './wo-board'

const row = (over: Partial<WoBoardRow>): WoBoardRow => ({
  id: 'W1',
  code: 'WO1',
  product: 'P1',
  status: 'in_progress',
  planned: 100,
  started: 60,
  completed: 20,
  wip: 40,
  scrapped: 0,
  lots: 2,
  progress: 0.2,
  due_date: '2026-10-01',
  days_left: -3,
  risk: 'overdue',
  wip_by_op: [{ operation: 'OP10', qty: 40 }],
  ...over,
})

const ROWS = [
  row({}),
  row({ id: 'W2', code: 'WO2', risk: 'at_risk', days_left: 2 }),
  row({ id: 'W3', code: 'WO3', risk: 'ok', days_left: 20 }),
]

async function show(url = '/') {
  const spy = vi.spyOn(woApi, 'board').mockResolvedValue(ROWS)
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
          <WoBoard />
        </SidebarProvider>
      ),
    }),
    history: createMemoryHistory({ initialEntries: [url] }),
  })
  const s = await render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  return { s, spy }
}

afterEach(() => vi.restoreAllMocks())

describe('工单进度看板', () => {
  it('显示逾期 / 临近交期计数、在制分布与交期状态', async () => {
    const { s } = await show()
    await expect.element(s.getByText('WO3')).toBeVisible()
    await expect
      .element(s.getByText(`${t('mes.woBoard.risk.overdue')} 1`))
      .toBeVisible()
    await expect
      .element(s.getByText(`${t('mes.woBoard.risk.at_risk')} 1`))
      .toBeVisible()
    expect(s.getByText('OP10:40').elements()).toHaveLength(3)
    expect(s.getByText('20 / 40 / 0 / 100').elements()).toHaveLength(3)
  })

  it('按交期状态筛选', async () => {
    const { s } = await show('/?risk=at_risk')
    await expect.element(s.getByText('WO2')).toBeVisible()
    expect(s.getByText('WO1').elements()).toHaveLength(0)
    expect(s.getByText('WO3').elements()).toHaveLength(0)
  })

  it('修改预警天数后按新天数重新查询', async () => {
    const { s, spy } = await show()
    await expect.element(s.getByText('WO1')).toBeVisible()
    expect(spy).toHaveBeenLastCalledWith(undefined)
    await userEvent.fill(s.getByPlaceholder(t('mes.woBoard.ruleDefault')), '5')
    await expect.poll(() => spy.mock.lastCall?.[0]).toBe(5)
  })
})
