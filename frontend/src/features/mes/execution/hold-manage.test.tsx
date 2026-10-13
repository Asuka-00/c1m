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
import { mesApi } from '@/lib/api/mes/common'
import { execApi, type HoldRow } from '@/lib/api/mes/execution'
import { SidebarProvider } from '@/components/ui/sidebar'
import { enumLabel, reasonOptLabel } from '@/features/mes/common/labels'
import HoldManagePage from './hold-manage'

const row = (over: Partial<HoldRow> = {}): HoldRow => ({
  id: 'H1',
  lot_id: 'L1',
  lot: 'LOT1',
  product: null,
  step_seq: 1,
  reason: 'QC',
  reason_name: 'QC',
  source: 'manual',
  hold_type: 'manual',
  held_at: null,
  held_by: null,
  is_active: true,
  hours: null,
  comment: null,
  released_at: null,
  released_by: null,
  release_reason: null,
  release_comment: null,
  ...over,
})

async function show(rows: HoldRow[]) {
  const spy = vi
    .spyOn(execApi, 'holds')
    .mockResolvedValue({ data: rows, count: rows.length })
  vi.spyOn(mesApi, 'list').mockResolvedValue({ data: [], count: 0 } as never)
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
          <HoldManagePage />
        </SidebarProvider>
      ),
    }),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  const s = await render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  return { s, spy }
}

afterEach(() => vi.restoreAllMocks())

describe('Hold 列表：显示终态批次开关（N6 / P15 A）', () => {
  it('默认关闭、不带 include_terminal；打开后带 include_terminal=true', async () => {
    const { s, spy } = await show([row()])
    await expect.poll(() => spy.mock.calls.length).toBeGreaterThan(0)
    expect(spy.mock.calls[0][0]).not.toHaveProperty('include_terminal')
    const sw = s.getByTestId('show-terminal')
    await expect.element(sw).toHaveAttribute('aria-checked', 'false')
    await userEvent.click(sw)
    await expect
      .poll(() => spy.mock.calls.some((c) => c[0].include_terminal === 'true'))
      .toBe(true)
  })

  it('有 lot_status 时显示本地化状态列', async () => {
    const { s } = await show([
      row({ lot_status: 'scrapped' }),
      row({ id: 'H2', lot: 'LOT2', lot_status: 'waiting' }),
    ])
    await expect
      .element(
        s.getByText(enumLabel('lot_status', 'scrapped'), { exact: true })
      )
      .toBeVisible()
    await expect
      .poll(
        () => document.querySelectorAll('[data-testid=hold-lot-status]').length
      )
      .toBe(2)
  })

  it('旧接口没有 lot_status 时不显示状态列', async () => {
    const { s } = await show([row()])
    await expect.element(s.getByText('LOT1')).toBeVisible()
    expect(document.querySelector('[data-testid=hold-lot-status]')).toBeNull()
  })

  it('开关文案说明默认隐藏的是已报废 / 已出货 / 已合并（修订版 N6）', async () => {
    const { s } = await show([row({ lot_status: 'completed' })])
    await expect
      .element(s.getByText(t('mes.holdrel.showTerminal')))
      .toBeVisible()
    await expect
      .element(
        s.getByText(enumLabel('lot_status', 'completed'), { exact: true })
      )
      .toBeVisible()
  })

  it('qtime_expired 原因码显示本地化名称（M1）', async () => {
    const { s } = await show([
      row({ reason: 'qtime_expired', reason_name: 'QT' }),
    ])
    await expect
      .element(
        s.getByText(reasonOptLabel({ code: 'qtime_expired', name: 'QT' }))
      )
      .toBeVisible()
  })
})
