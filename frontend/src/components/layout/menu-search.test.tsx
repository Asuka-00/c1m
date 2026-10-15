import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import i18n, { t } from '@/i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { api, type MenuNode, type MyMenus } from '@/lib/api'
import { MenuBreadcrumb } from './menu-breadcrumb'
import { breadcrumbOf, matchEntries, menuEntries } from './menu-index'
import { MenuSearch } from './menu-search'

const node = (x: Partial<MenuNode> & { key: string }): MenuNode =>
  ({ title: x.key, path: null, icon: null, children: [], ...x }) as MenuNode

// 模拟 /menus/me（已按权限过滤：没有投产、通知订阅等）
const MENUS: MenuNode[] = [
  node({
    key: 'g-execution',
    title: 'Lot Operation',
    children: [
      node({
        key: 'mes-lot-console',
        title: 'Lot Operation',
        path: '/mes/lot-console',
      }),
      node({
        key: 'mes-qtime-monitor',
        title: 'Q-Time Monitor',
        path: '/mes/qtime-monitor',
      }),
    ],
  }),
  node({
    key: 'g-equipment',
    title: 'Tool Management',
    children: [
      node({
        key: 'mes-eqp-board',
        title: 'Tool Status Board',
        path: '/mes/eqp-board',
      }),
      node({
        key: 'mes-equipment-master',
        title: 'Equipment Master',
        path: '/mes/equipment-master',
        tabs: [
          {
            key: 'mes-equipment',
            title: 'Equipment',
            component: null,
            permission: null,
          },
          {
            key: 'mes-equipment_type',
            title: 'Equipment Type',
            component: null,
            permission: null,
          },
        ],
      }),
    ],
  }),
  node({
    key: 'g-test',
    title: 'Test',
    children: [
      node({
        key: 'x-same',
        title: 'Same Name',
        path: '/x/same',
        tabs: [
          {
            key: 'x-same-tab',
            title: 'Same Name',
            component: null,
            permission: null,
          },
        ],
      }),
    ],
  }),
]

describe('menuEntries / matchEntries', () => {
  const entries = menuEntries(MENUS)
  const ids = (q: string) => matchEntries(entries, q).map((e) => e.id)

  it('只索引下发的菜单与页签，不额外加入消息中心 / 个人设置', () => {
    expect(entries.map((e) => e.id)).toEqual([
      'mes-lot-console',
      'mes-qtime-monitor',
      'mes-eqp-board',
      'mes-equipment-master:mes-equipment',
      'mes-equipment-master:mes-equipment_type',
      'x-same:x-same-tab',
    ])
    expect(ids('notification')).toEqual([])
    expect(ids('個人設定')).toEqual([])
    // 未下发（无权限）的菜单搜不到
    expect(ids('lot-start')).toEqual([])
    expect(ids('投片')).toEqual([])
  })

  it('当前语言为英文时，中文 / 日文标题与 key 都能匹配', () => {
    expect(i18n.language).toBe('en')
    expect(ids('机台状态')).toEqual(['mes-eqp-board'])
    expect(ids('Q-Time 監視')).toEqual(['mes-qtime-monitor'])
    expect(ids('qtime-monitor')).toEqual(['mes-qtime-monitor'])
    expect(ids('tool status')).toEqual(['mes-eqp-board'])
  })

  it('页签可按页签名或所属合并菜单名匹配', () => {
    expect(ids('设备类型')).toEqual(['mes-equipment-master:mes-equipment_type'])
    expect(ids('机台主数据')).toEqual([
      'mes-equipment-master:mes-equipment',
      'mes-equipment-master:mes-equipment_type',
    ])
  })
})

describe('breadcrumbOf', () => {
  it('分组 › 菜单 › 页签', () => {
    expect(
      breadcrumbOf(MENUS, '/mes/equipment-master', 'mes-equipment_type').map(
        (c) => c.title
      )
    ).toEqual([
      t('menu.g-equipment'),
      t('menu.mes-equipment-master'),
      t('menu.mes-equipment_type'),
    ])
  })

  it('合并菜单与页签同名时只显示一次', () => {
    expect(breadcrumbOf(MENUS, '/x/same').map((c) => c.title)).toEqual([
      'Test',
      'Same Name',
    ])
  })

  it('不在菜单树里的页面只显示自身标题，未知路由为空', () => {
    expect(breadcrumbOf(MENUS, '/settings')).toEqual([
      { key: 'settings', title: t('menu.settings') },
    ])
    expect(breadcrumbOf(MENUS, '/no/such/page')).toEqual([])
  })
})

describe('MenuSearch / MenuBreadcrumb', () => {
  afterEach(() => vi.restoreAllMocks())

  async function show(path = '/') {
    vi.spyOn(api, 'myMenus').mockResolvedValue({
      menus: MENUS,
      forbidden_paths: [],
      permissions: [],
      tenant_id: null,
      is_superuser: false,
    } as MyMenus)
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const router = createRouter({
      routeTree: createRootRoute({
        component: () => (
          <div>
            <input data-testid='other-input' />
            <MenuBreadcrumb />
            <MenuSearch />
          </div>
        ),
      }),
      history: createMemoryHistory({ initialEntries: [path] }),
    })
    const s = await render(
      <QueryClientProvider client={qc}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    )
    return { s, router }
  }

  const dialog = () => document.querySelector('[role=dialog]')

  it('Ctrl+K 全局打开（输入框内也生效），再按一次关闭', async () => {
    const { s } = await show()
    await s.getByTestId('other-input').click()
    await userEvent.keyboard('{Control>}k{/Control}')
    await expect.poll(dialog).not.toBeNull()
    await userEvent.keyboard('{Control>}k{/Control}')
    await expect.poll(dialog).toBeNull()
    await userEvent.keyboard('{Meta>}k{/Meta}')
    await expect.poll(dialog).not.toBeNull()
  })

  it('选中页签项跳转到合并页并定位页签；面包屑随之更新', async () => {
    const { s, router } = await show()
    await s.getByTestId('menu-search-open').click()
    await userEvent.keyboard('设备类型')
    await s
      .getByTestId('menu-hit-mes-equipment-master:mes-equipment_type')
      .click()
    await expect
      .poll(() => router.state.location.pathname)
      .toBe('/mes/equipment-master')
    expect(router.state.location.search).toEqual({ tab: 'mes-equipment_type' })
    await expect
      .element(s.getByTestId('breadcrumb'))
      .toHaveTextContent(t('menu.mes-equipment_type'))
  })

  it('Esc 关闭搜索框', async () => {
    const { s } = await show()
    await s.getByTestId('menu-search-open').click()
    await expect.poll(dialog).not.toBeNull()
    await userEvent.keyboard('{Escape}')
    await expect.poll(dialog).toBeNull()
  })

  it('方向键 + 回车选中跳转', async () => {
    const { s, router } = await show()
    await s.getByTestId('menu-search-open').click()
    await userEvent.keyboard('mes-')
    await expect
      .element(s.getByTestId('menu-hit-mes-lot-console'))
      .toHaveAttribute('data-selected', 'true')
    await userEvent.keyboard('{ArrowDown}')
    await expect
      .element(s.getByTestId('menu-hit-mes-qtime-monitor'))
      .toHaveAttribute('data-selected', 'true')
    await userEvent.keyboard('{Enter}')
    await expect
      .poll(() => router.state.location.pathname)
      .toBe('/mes/qtime-monitor')
    await expect.poll(dialog).toBeNull()
  })

  it('无结果时显示 nav.searchMenuEmpty', async () => {
    const { s } = await show()
    await s.getByTestId('menu-search-open').click()
    await userEvent.keyboard('zzz-no-such-menu')
    await expect.element(s.getByText(t('nav.searchMenuEmpty'))).toBeVisible()
  })

  it('面包屑分隔符在 li 内且对读屏隐藏', async () => {
    const { s } = await show('/mes/equipment-master?tab=mes-equipment_type')
    await expect.element(s.getByTestId('breadcrumb')).toBeVisible()
    const ol = document.querySelector('[data-testid=breadcrumb] ol')!
    expect([...ol.children].every((c) => c.tagName === 'LI')).toBe(true)
    const seps = ol.querySelectorAll('svg')
    expect(seps.length).toBe(2)
    seps.forEach((x) => {
      expect(x.closest('li')).not.toBeNull()
      expect(x.getAttribute('aria-hidden')).toBe('true')
    })
  })

  it('未知路由不显示面包屑', async () => {
    await show('/no/such/page')
    await new Promise((r) => setTimeout(r, 100))
    expect(document.querySelector('[data-testid=breadcrumb]')).toBeNull()
  })
})
