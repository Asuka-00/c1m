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
import { execApi, type QueueRow } from '@/lib/api/mes/execution'
import { DispatchQueue } from './dispatch-queue'

const row = (over: Partial<QueueRow>): QueueRow => ({
  id: 'N1',
  code: 'LOT-N',
  product: 'P1',
  step_seq: 10,
  operation: 'OP10',
  operation_name: 'etch',
  step_id: 'S10',
  lot_status: 'waiting',
  equipment_id: null,
  carrier: null,
  qty: 25,
  priority: 'NORMAL',
  priority_level: 5,
  priority_color: null,
  hot: false,
  on_hold: false,
  qtime_remaining: null,
  hours: 1,
  ...over,
})

async function show(url = '/') {
  vi.spyOn(execApi, 'queue').mockResolvedValue([
    row({
      id: 'H1',
      code: 'LOT-H',
      priority: 'HOT',
      priority_level: 1,
      hot: true,
    }),
    row({}),
  ])
  const onLot = vi.fn()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms: [],
  })
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => <DispatchQueue onLot={onLot} />,
    }),
    history: createMemoryHistory({ initialEntries: [url] }),
  })
  const s = await render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  return { s, onLot }
}

afterEach(() => vi.restoreAllMocks())

describe('在制队列：急件', () => {
  it('急件带火焰标记，点击批次进入作业', async () => {
    const { s, onLot } = await show()
    await expect.element(s.getByText('LOT-N')).toBeVisible()
    expect(s.getByLabelText(t('mes.queue.hot')).elements()).toHaveLength(1)
    await userEvent.click(s.getByText('LOT-N'))
    expect(onLot).toHaveBeenCalledWith('N1')
  })

  it('只看急件', async () => {
    const { s } = await show('/?hot=true')
    await expect.element(s.getByText('LOT-H')).toBeVisible()
    expect(s.getByText('LOT-N').elements()).toHaveLength(0)
  })
})
