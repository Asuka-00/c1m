import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import i18n, { t } from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { SidebarProvider } from '@/components/ui/sidebar'
import { ForbiddenError } from './forbidden'

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

async function show(inApp: boolean) {
  const router = createRouter({
    routeTree: createRootRoute({
      component: () =>
        inApp ? (
          <SidebarProvider>
            <ForbiddenError inApp />
          </SidebarProvider>
        ) : (
          <ForbiddenError />
        ),
    }),
    history: createMemoryHistory({ initialEntries: ['/mes/secret'] }),
  })
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false, enabled: false } },
        })
      }
    >
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

describe('403 页面顶栏（FE-02）', () => {
  it('登录后布局内的 403 带顶栏（侧栏开关），内容照常显示', async () => {
    const s = await show(true)
    await expect.element(s.getByTestId('forbidden-header')).toBeVisible()
    await expect
      .element(s.getByRole('button', { name: t('sidebar.toggle') }))
      .toBeVisible()
    await expect.element(s.getByText(t('errors.403.title'))).toBeVisible()
  })

  it('独立 /403 路由（不在侧栏布局内）不带顶栏', async () => {
    const s = await show(false)
    await expect.element(s.getByText(t('errors.403.title'))).toBeVisible()
    expect(document.querySelector('[data-testid=forbidden-header]')).toBeNull()
  })
})
