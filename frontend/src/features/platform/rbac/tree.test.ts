import { describe, expect, it } from 'vitest'
import type { PermNode } from '@/lib/api'
import { allIds, checkState, filterTree, nodeCodes, toggleNode } from './tree'

const node = (
  id: string,
  kind: PermNode['kind'],
  code = '',
  children: PermNode[] = []
): PermNode => ({
  id,
  kind,
  type: kind === 'perm' ? 'BUTTON' : 'MENU',
  key: null,
  name: id,
  code,
  path: null,
  icon: null,
  component: null,
  sort_order: 0,
  visible: true,
  status: 'active',
  scope: null,
  space: null,
  description: null,
  menu_id: null,
  children,
})

const tree = node('sys', 'menu', '', [
  node('users', 'menu', '', [
    node('ur', 'perm', 'users:read'),
    node('uw', 'perm', 'users:write'),
  ]),
  node('roles', 'menu', '', [node('rr', 'perm', 'roles:read')]),
])

describe('权限树工具', () => {
  it('收集后代编码', () => {
    expect(nodeCodes(tree).sort()).toEqual([
      'roles:read',
      'users:read',
      'users:write',
    ])
  })
  it('三态状态', () => {
    expect(checkState(tree, new Set())).toBe(false)
    expect(checkState(tree, new Set(['users:read']))).toBe('indeterminate')
    expect(
      checkState(tree.children[0], new Set(['users:read', 'users:write']))
    ).toBe(true)
  })
  it('勾选父节点作用于全部后代，且不修改入参', () => {
    const before = new Set(['x'])
    const on = toggleNode(tree, before, true)
    expect([...on].sort()).toEqual([
      'roles:read',
      'users:read',
      'users:write',
      'x',
    ])
    expect([...before]).toEqual(['x'])
    expect([...toggleNode(tree.children[0], on, false)].sort()).toEqual([
      'roles:read',
      'x',
    ])
  })
  it('关键字过滤保留祖先', () => {
    const r = filterTree([tree], 'roles:read')
    expect(r[0].children.map((c) => c.id)).toEqual(['roles'])
    expect(filterTree([tree], '')).toEqual([tree])
    expect(filterTree([tree], 'nope')).toEqual([])
  })
  it('全部 id', () => {
    expect(allIds([tree])).toHaveLength(6)
  })
})
