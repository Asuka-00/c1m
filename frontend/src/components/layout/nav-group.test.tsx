import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import '@/styles/index.css'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { SidebarProvider } from '@/components/ui/sidebar'
import { NavGroup } from './nav-group'

const LONG = 'Future Hold（预约 Hold）'

function Harness() {
  return (
    <SidebarProvider>
      {/* 与侧栏展开宽度（17.5rem）相当，按钮内还要扣掉子菜单缩进 */}
      <div style={{ width: 280 }}>
        <NavGroup
          title='MES'
          items={[
            {
              key: 'g-exception',
              title: '异常处置',
              items: [
                { title: LONG, url: '/mes/future-hold' },
                { title: 'Interlock Log', url: '/mes/interlock-log' },
              ],
            },
          ]}
        />
      </div>
    </SidebarProvider>
  )
}

describe('NavGroup 子菜单长名称', () => {
  it('当前分组展开时，长名称单行完整显示、不截断不折行（FE-02）', async () => {
    const rootRoute = createRootRoute({ component: Harness })
    const router = createRouter({
      routeTree: rootRoute,
      history: createMemoryHistory({ initialEntries: ['/mes/future-hold'] }),
    })
    const screen = await render(<RouterProvider router={router} />)
    const link = screen.getByRole('link', { name: LONG })
    await expect.element(link).toBeVisible()
    const el = link.element() as HTMLElement
    const span = el.querySelector('span') as HTMLElement
    // 没有被截断：内容宽度不超过可见宽度；只有一行
    expect(span.scrollWidth).toBeLessThanOrEqual(span.clientWidth + 1)
    expect(getComputedStyle(span).whiteSpace).toBe('nowrap')
    const range = document.createRange()
    range.selectNodeContents(span)
    expect(range.getClientRects().length).toBe(1)
    // 文字全部可见，不需要只靠悬停才能看到的 title
    expect(el.getAttribute('title')).toBeNull()
  })
})
