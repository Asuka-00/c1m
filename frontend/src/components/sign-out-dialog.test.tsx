import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { SignOutDialog } from './sign-out-dialog'

const navigate = vi.fn()
const reset = vi.fn()

const MOCK_HREF = 'https://app.test/dashboard?tab=1'

// 组件以 selector 读取 store：useAuthStore((s) => s.reset)
vi.mock('@/stores/auth-store', () => ({
  useAuthStore: <T,>(sel: (s: { reset: () => void }) => T) => sel({ reset }),
}))

/** 在 QueryClientProvider 内渲染，返回 client 以断言缓存被清空。 */
async function renderDialog() {
  const qc = new QueryClient()
  qc.setQueryData(['me'], { id: 1 })
  const r = await render(
    <QueryClientProvider client={qc}>
      <SignOutDialog open onOpenChange={vi.fn()} />
    </QueryClientProvider>
  )
  return { ...r, qc }
}

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => navigate,
    useLocation: () => ({ href: MOCK_HREF }),
  }
})

describe('SignOutDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls auth.reset and navigates to sign-in with current location as redirect', async () => {
    const { getByRole, qc } = await renderDialog()

    await userEvent.click(getByRole('button', { name: /^Sign out$/i }))

    expect(reset).toHaveBeenCalledOnce()
    expect(qc.getQueryData(['me'])).toBeUndefined() // 会话缓存已清空
    expect(navigate).toHaveBeenCalledWith({
      to: '/sign-in',
      search: { redirect: MOCK_HREF },
      replace: true,
    })
  })

  it('does not call reset or navigate when Cancel is clicked', async () => {
    const { getByRole, qc } = await renderDialog()

    await userEvent.click(getByRole('button', { name: /^Cancel$/i }))

    expect(reset).not.toHaveBeenCalled()
    expect(qc.getQueryData(['me'])).toEqual({ id: 1 })
    expect(navigate).not.toHaveBeenCalled()
  })
})
