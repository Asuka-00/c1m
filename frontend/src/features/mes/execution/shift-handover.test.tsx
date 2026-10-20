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
import { shiftLogApi, type ShiftLog } from '@/lib/api/mes/shift-log'
import { SidebarProvider } from '@/components/ui/sidebar'
import ShiftHandover from './shift-handover'

const log = (over: Partial<ShiftLog>): ShiftLog => ({
  id: 'S1',
  shift_date: '2026-10-19',
  shift: 'D',
  shift_name: 'Day',
  area: null,
  summary: 'etch PM done',
  open_items: 'CMP alarm',
  handed_by: 'alice',
  handed_at: null,
  log_status: 'open',
  received_by: null,
  received_at: null,
  receive_comment: null,
  ...over,
})

async function show(perms: string[]) {
  vi.spyOn(shiftLogApi, 'list').mockResolvedValue([
    log({}),
    log({
      id: 'S2',
      summary: 'night shift quiet',
      open_items: null,
      log_status: 'acknowledged',
      received_by: 'bob',
    }),
  ])
  vi.spyOn(mesApi, 'list').mockResolvedValue({ data: [], count: 0 } as never)
  const ack = vi.spyOn(shiftLogApi, 'ack').mockResolvedValue(log({}))
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms,
  })
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => (
        <SidebarProvider>
          <ShiftHandover />
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
  return { s, ack }
}

afterEach(() => vi.restoreAllMocks())

describe('交接班日志', () => {
  it('只有未接班的日志可确认，确认时带接班备注', async () => {
    const { s, ack } = await show(['mes.exec:write'])
    await expect.element(s.getByText('night shift quiet')).toBeVisible()
    await expect.element(s.getByText('CMP alarm')).toBeVisible()
    await expect.element(s.getByText('bob')).toBeVisible()
    const btns = s.getByRole('button', { name: t('mes.shiftLog.ack') })
    expect(btns.elements()).toHaveLength(1)
    await userEvent.click(btns.first())
    const dlg = s.getByRole('alertdialog')
    await userEvent.fill(
      dlg.getByLabelText(t('mes.shiftLog.ackComment')),
      'got it'
    )
    await userEvent.click(
      dlg.getByRole('button', { name: t('mes.shiftLog.ack') })
    )
    await expect.poll(() => ack.mock.calls[0]).toEqual(['S1', 'got it'])
  })

  it('无作业权限时不能交班或接班', async () => {
    const { s } = await show([])
    await expect.element(s.getByText('etch PM done')).toBeVisible()
    expect(
      s.getByRole('button', { name: t('mes.shiftLog.ack') }).elements()
    ).toHaveLength(0)
    expect(s.getByTestId('new-handover').elements()).toHaveLength(0)
  })
})
