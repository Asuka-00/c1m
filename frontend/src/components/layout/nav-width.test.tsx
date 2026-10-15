/**
 * FE-02：侧栏菜单名中英日都单行完整显示（不截断、不折行）。
 * 用真实的 Sidebar（默认宽度 17.5rem）渲染全部 MES 菜单名：分组标题作一级（带图标和箭头），
 * 其余作二级子菜单；逐个检查文字右边缘不越过箭头 / 按钮内边距，且只有一行高。
 */
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import en from '@/i18n/locales/mes/en.json'
import ja from '@/i18n/locales/mes/ja.json'
import zh from '@/i18n/locales/mes/zh-CN.json'
import '@/styles/index.css'
import { Warehouse } from 'lucide-react'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import {
  Sidebar,
  SidebarContent,
  SidebarProvider,
} from '@/components/ui/sidebar'
import { NavGroup } from './nav-group'

const FILES = { 'zh-CN': zh, en, ja } as const

/** 文字超出可用宽度或折成多行的菜单名。 */
function overflowing(): string[] {
  const bad: string[] = []
  document
    .querySelectorAll<HTMLElement>(
      '[data-sidebar] a > span, [data-sidebar] button > span'
    )
    .forEach((s) => {
      const btn = s.parentElement as HTMLElement
      const sr = s.getBoundingClientRect()
      const br = btn.getBoundingClientRect()
      const arrow = Array.from(btn.querySelectorAll('svg')).find(
        (x) => x.getBoundingClientRect().left >= sr.left
      )
      const limit =
        arrow?.getBoundingClientRect().left ??
        br.right - parseFloat(getComputedStyle(btn).paddingRight)
      const range = document.createRange()
      range.selectNodeContents(s)
      const text = range.getBoundingClientRect()
      const lines = range.getClientRects().length
      if (
        text.right > limit + 0.5 ||
        lines > 1 ||
        s.scrollWidth > s.clientWidth + 1
      )
        bad.push(s.textContent ?? '')
    })
  return bad
}

describe('侧栏菜单名单行完整显示（FE-02）', () => {
  for (const [lang, file] of Object.entries(FILES)) {
    it(lang, async () => {
      const menu = (file as unknown as { menu: Record<string, string> }).menu
      const groups = Object.entries(menu).filter(
        ([k, v]) => k.startsWith('g-') && v
      )
      const leaves = Object.entries(menu).filter(
        ([k, v]) => !k.startsWith('g-') && v
      )
      const items = groups.map(([k, v], i) => ({
        key: k,
        title: v,
        icon: Warehouse,
        items:
          i === 0
            ? leaves.map(([lk, lv]) => ({ title: lv, url: `/${lk}` }))
            : [{ title: '·', url: `/x${i}` }],
      }))
      const router = createRouter({
        routeTree: createRootRoute({
          component: () => (
            <SidebarProvider>
              <Sidebar collapsible='none'>
                <SidebarContent>
                  <NavGroup title='MES' items={items} />
                </SidebarContent>
              </Sidebar>
            </SidebarProvider>
          ),
        }),
        history: createMemoryHistory({
          initialEntries: [`/${leaves[0][0]}`],
        }),
      })
      const s = await render(<RouterProvider router={router} />)
      await expect
        .element(s.getByRole('link', { name: leaves[0][1], exact: true }))
        .toBeVisible()
      expect(overflowing()).toEqual([])
    })
  }
})
