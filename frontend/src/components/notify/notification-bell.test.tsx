import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { NotificationBell } from './notification-bell'

const navigate = vi.fn()
const read = vi.fn((_ids?: string[]) => Promise.resolve({ updated: 1 }))
const note = {
  id: 'n1',
  event_type: 'test.untranslated',
  event_label: 'Lot auto hold',
  severity: 'warning',
  title: 'Lot L-1 held',
  body: null,
  params: {},
  object_type: 'lot',
  object_id: 'l1',
  object_code: 'L-1',
  link: '/mes/lot-console?lot=l1',
  created_at: '2026-10-25T00:00:00Z',
  read_at: null,
  is_read: false,
}

vi.mock('@/lib/api', () => ({
  api: {
    notifications: {
      summary: () => Promise.resolve({ unread: 1, latest: [note] }),
      read: (ids?: string[]) => read(ids),
    },
  },
}))

vi.mock('@/lib/api/hooks', () => ({
  useCurrentTenant: () => ({ tenant: { id: 't1' } }),
}))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => navigate }
})

async function openBell() {
  const r = await render(
    <QueryClientProvider client={new QueryClient()}>
      <NotificationBell />
    </QueryClientProvider>
  )
  await expect.element(r.getByTestId('notify-badge')).toHaveTextContent('1')
  await userEvent.click(r.getByRole('button', { name: /^Notifications$/ }))
  return r
}

describe('NotificationBell', () => {
  beforeEach(() => vi.clearAllMocks())

  it('点击通知只跳转，不自动确认', async () => {
    const r = await openBell()
    await userEvent.click(r.getByText('Lot L-1 held'))
    expect(navigate).toHaveBeenCalledOnce()
    expect(read).not.toHaveBeenCalled()
  })

  it('点击确认才标记该条通知', async () => {
    const r = await openBell()
    await userEvent.click(r.getByRole('button', { name: /^Confirm$/ }))
    expect(read).toHaveBeenCalledWith(['n1'])
    expect(navigate).not.toHaveBeenCalled()
  })
})
