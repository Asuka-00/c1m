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
import { api, type PermNode } from '@/lib/api'
import { SidebarProvider } from '@/components/ui/sidebar'
import PermissionTreePage from './index'

const node = (id: string, name: string, children: PermNode[] = []) =>
  ({
    id,
    kind: children.length ? 'menu' : 'perm',
    type: children.length ? 'menu' : 'button',
    key: id,
    name,
    code: id,
    path: null,
    icon: null,
    component: null,
    sort_order: 0,
    visible: true,
    status: 'active',
    children,
  }) as unknown as PermNode

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(() => vi.restoreAllMocks())

describe('权限树展开按钮（FE-01 / FE-02）', () => {
  it('过滤状态下图标是展开的，提示和 aria-label 也显示「收起」', async () => {
    vi.spyOn(api.permissions, 'tree').mockResolvedValue([
      node('m1', 'Lot', [node('p1', 'lot-read')]),
    ])
    const router = createRouter({
      routeTree: createRootRoute({
        component: () => (
          <SidebarProvider>
            <PermissionTreePage />
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
    const collapse = s
      .getByRole('table')
      .getByRole('button', { name: t('common.collapse') })
    await expect.element(collapse).toBeVisible()
    await collapse.click()
    const expand = s
      .getByRole('table')
      .getByRole('button', { name: t('common.expand') })
    await expect.element(expand).toBeVisible()
    await userEvent.fill(s.getByPlaceholder(t('rbac.searchTree')), 'lot-read')
    // 过滤时子节点照常显示（图标为展开），提示与图标一致
    await expect.element(s.getByText('lot-read')).toBeVisible()
    await expect
      .element(
        s.getByRole('table').getByRole('button', { name: t('common.collapse') })
      )
      .toBeVisible()
  })
})
