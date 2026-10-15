import { describe, expect, it } from 'vitest'
import type { MenuNode, MenuTab } from '@/lib/api'
import { findPage, pickTab } from './merged'

const tab = (key: string): MenuTab => ({
  key,
  title: key,
  component: `mes:${key}`,
  permission: null,
})

describe('pickTab', () => {
  const tabs = [tab('a'), tab('b')]
  it('URL 中的页签可见时选中它', () => {
    expect(pickTab(tabs, 'b')?.key).toBe('b')
  })
  it('未知或缺省时取第一个页签', () => {
    expect(pickTab(tabs, 'x')?.key).toBe('a')
    expect(pickTab(tabs, undefined)?.key).toBe('a')
    expect(pickTab([], 'a')).toBeUndefined()
  })
})

describe('findPage', () => {
  const node = (
    key: string,
    path: string | null,
    extra: Partial<MenuNode> = {}
  ): MenuNode => ({ key, title: key, path, children: [], ...extra }) as MenuNode
  const menus = [
    node('g', null, {
      children: [
        node('mes-lot-console', '/mes/lot-console'),
        node('mes-check-config', '/mes/check-config', {
          tabs: [tab('mes-check_rule')],
        }),
      ],
    }),
  ]
  it('独立菜单返回路径，页签返回合并页与 tab', () => {
    expect(findPage(menus, 'mes-lot-console')).toEqual({
      path: '/mes/lot-console',
    })
    expect(findPage(menus, 'mes-check_rule')).toEqual({
      path: '/mes/check-config',
      tab: 'mes-check_rule',
    })
  })
  it('不可见时返回 null', () => {
    expect(findPage(menus, 'mes-x')).toBeNull()
  })
})
