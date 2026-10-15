import { describe, expect, it } from 'vitest'
import {
  type AccordionNode,
  activeChain,
  chainOf,
  matchesPath,
  toggleGroup,
} from './accordion'

const tree: AccordionNode[] = [
  { id: 'home', url: '/' },
  {
    id: 'exec',
    children: [
      { id: 'lot', url: '/mes/lot' },
      { id: 'hold', url: '/mes/lot-hold' },
    ],
  },
  {
    id: 'master',
    children: [
      { id: 'uom', url: '/mes/uom' },
      {
        id: 'nested',
        children: [
          { id: 'a', url: '/mes/a' },
          { id: 'deep', children: [{ id: 'b', url: '/mes/b' }] },
        ],
      },
      { id: 'sib', children: [{ id: 'c', url: '/mes/c' }] },
    ],
  },
]

describe('matchesPath', () => {
  it('完全匹配 / 下级路径 / 忽略查询参数', () => {
    expect(matchesPath('/mes/lot?page=2', '/mes/lot')).toBe(true)
    expect(matchesPath('/mes/lot/x', '/mes/lot')).toBe(true)
    expect(matchesPath('/mes/lot-hold', '/mes/lot')).toBe(false)
    expect(matchesPath('/mes/x', '/')).toBe(false)
    expect(matchesPath('/', '#')).toBe(false)
  })
})

describe('activeChain', () => {
  it('返回当前页面所在分组', () => {
    expect(activeChain(tree, '/mes/lot-hold')).toEqual(['exec'])
  })
  it('多级分组返回完整祖先链', () => {
    expect(activeChain(tree, '/mes/b')).toEqual(['master', 'nested', 'deep'])
    expect(activeChain(tree, '/mes/a?tab=x')).toEqual(['master', 'nested'])
  })
  it('顶层链接或未知路径为空', () => {
    expect(activeChain(tree, '/')).toEqual([])
    expect(activeChain(tree, '/nope')).toEqual([])
  })
})

describe('toggleGroup', () => {
  it('展开一个分组时收起其他分组', () => {
    expect(toggleGroup(tree, ['exec'], 'master', true)).toEqual(['master'])
  })
  it('展开嵌套分组保留祖先链、收起同级', () => {
    const open = toggleGroup(tree, ['master', 'nested', 'deep'], 'sib', true)
    expect(open).toEqual(['master', 'sib'])
  })
  it('再次点击已展开分组时收起它及其下级', () => {
    expect(toggleGroup(tree, ['exec'], 'exec', false)).toEqual([])
    expect(
      toggleGroup(tree, ['master', 'nested', 'deep'], 'nested', false)
    ).toEqual(['master'])
  })
  it('收起未展开的分组不改变状态', () => {
    expect(toggleGroup(tree, ['exec'], 'master', false)).toEqual(['exec'])
  })
  it('chainOf 找不到时为空', () => {
    expect(chainOf(tree, 'zzz')).toEqual([])
  })
})
