import { describe, expect, it } from 'vitest'
import type { MenuTab } from '@/lib/api'
import { pickTab, resolveRedirect } from './merged'

const tab = (key: string): MenuTab => ({
  key,
  title: key,
  path: `/old/${key}`,
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

describe('resolveRedirect', () => {
  const r = { '/mes/check-rule': '/mes/check-config?tab=mes-check_rule' }
  it('旧路径跳转到合并页并保留原查询参数', () => {
    expect(resolveRedirect(r, '/mes/check-rule', { id: '1' })).toEqual({
      path: '/mes/check-config',
      search: { id: '1', tab: 'mes-check_rule' },
    })
  })
  it('非旧路径返回 null', () => {
    expect(resolveRedirect(r, '/mes/x')).toBeNull()
    expect(resolveRedirect(undefined, '/mes/check-rule')).toBeNull()
  })
})
