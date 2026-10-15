/** 侧栏手风琴：纯函数（展开链计算），便于单元测试。 */

/** 侧栏树节点（分组含 children，叶子含 url）。 */
export interface AccordionNode {
  id: string
  url?: string
  children?: AccordionNode[]
}

/**
 * 路径是否命中菜单链接（完全匹配或其下级路径，忽略查询参数）。
 *
 * @param path - 当前路径（可含查询参数）
 * @param url - 菜单链接
 */
export function matchesPath(path: string, url: string | undefined): boolean {
  if (!url || url === '#') return false
  const p = path.split('?')[0]
  return p === url || (url !== '/' && p.startsWith(`${url}/`))
}

/**
 * 当前页面所在分组的祖先链（自顶层分组到直接父分组的 id）。
 *
 * @param nodes - 侧栏树
 * @param path - 当前路径
 * @returns 祖先分组 id；当前页面不在任何分组内时为空
 */
export function activeChain(nodes: AccordionNode[], path: string): string[] {
  for (const n of nodes) {
    if (n.children?.length) {
      const sub = activeChain(n.children, path)
      if (
        sub.length ||
        n.children.some((c) => !c.children && matchesPath(path, c.url))
      )
        return [n.id, ...sub]
    }
  }
  return []
}

/**
 * 分组 id 的祖先链（含自身）；未找到时为空。
 *
 * @param nodes - 侧栏树
 * @param id - 分组 id
 */
export function chainOf(nodes: AccordionNode[], id: string): string[] {
  for (const n of nodes) {
    if (n.id === id) return [n.id]
    if (n.children?.length) {
      const sub = chainOf(n.children, id)
      if (sub.length) return [n.id, ...sub]
    }
  }
  return []
}

/**
 * 切换分组：展开时只保留该分组及其祖先（同级及其他分组收起）；
 * 收起时移除该分组及其所有下级。
 *
 * @param nodes - 侧栏树
 * @param open - 当前展开的分组 id（祖先链）
 * @param id - 被点击的分组
 * @param next - 目标状态（true 展开）
 * @returns 新的展开 id 列表
 */
export function toggleGroup(
  nodes: AccordionNode[],
  open: string[],
  id: string,
  next: boolean
): string[] {
  const chain = chainOf(nodes, id)
  if (next) return chain
  const i = open.indexOf(id)
  return i < 0 ? open : open.slice(0, i)
}
