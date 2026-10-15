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
      {/* 与侧栏展开宽度（16rem）相当，按钮内还要扣掉子菜单缩进 */}
      <div style={{ width: 200 }}>
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
  it('当前分组展开时，长名称换行显示完整、不截断，并带悬停全文', async () => {
    const rootRoute = createRootRoute({ component: Harness })
    const router = createRouter({
      routeTree: rootRoute,
      history: createMemoryHistory({ initialEntries: ['/mes/future-hold'] }),
    })
    const screen = await render(<RouterProvider router={router} />)
    const link = screen.getByRole('link', { name: LONG })
    await expect.element(link).toBeVisible()
    const el = link.element() as HTMLElement
    expect(el.getAttribute('title')).toBe(LONG)
    const span = el.querySelector('span') as HTMLElement
    // 没有被截断：内容宽度不超过可见宽度
    expect(span.scrollWidth).toBeLessThanOrEqual(span.clientWidth + 1)
    expect(getComputedStyle(span).whiteSpace).toBe('normal')
    // 换成两行后按钮高度随内容增长，文字不溢出按钮
    expect(el.scrollHeight).toBeLessThanOrEqual(el.clientHeight + 1)
  })
})
