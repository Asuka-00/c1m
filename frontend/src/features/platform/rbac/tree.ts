/** 统一权限树的纯函数工具（三态勾选、编码收集）。 */
import { t } from '@/i18n'
import type { PermNode } from '@/lib/api'
import { permLabel } from '@/lib/rbac-labels'

/**
 * 节点显示名称：菜单按 menu.<key> 本地化（与侧边栏一致），虚拟分组使用本地化名称。
 *
 * @param n - 权限树节点
 * @returns 当前语言下的名称
 */
export function nodeLabel(n: PermNode): string {
  if (n.kind === 'group') return t('rbac.otherPerms')
  if (n.kind === 'menu' && n.key)
    return t(`menu.${n.key}`, { defaultValue: n.name })
  return n.kind === 'perm' ? permLabel(n.code, n.name) : n.name
}

/** 复选框状态：全选 / 未选 / 半选。 */
export type CheckState = boolean | 'indeterminate'

/**
 * 收集节点自身及全部后代中的权限编码（菜单节点本身没有编码）。
 *
 * @param node - 权限树节点
 * @returns 去重后的权限编码
 */
export function nodeCodes(node: PermNode): string[] {
  const out = new Set<string>()
  const walk = (n: PermNode) => {
    if (n.kind === 'perm' && n.code) out.add(n.code)
    n.children.forEach(walk)
  }
  walk(node)
  return [...out]
}

/**
 * 计算节点的三态勾选状态。
 *
 * @param node - 权限树节点
 * @param selected - 已选权限编码
 * @returns 全部选中为 true，部分为 'indeterminate'，否则 false
 */
export function checkState(node: PermNode, selected: Set<string>): CheckState {
  const codes = nodeCodes(node)
  const n = codes.filter((c) => selected.has(c)).length
  if (n === 0) return false
  return n === codes.length ? true : 'indeterminate'
}

/**
 * 勾选 / 取消节点：同时作用于其全部后代权限编码。
 *
 * @param node - 被点击的节点
 * @param selected - 当前已选编码
 * @param on - true 为勾选
 * @returns 新的已选编码集合（不修改入参）
 */
export function toggleNode(
  node: PermNode,
  selected: Set<string>,
  on: boolean
): Set<string> {
  const next = new Set(selected)
  nodeCodes(node).forEach((c) => (on ? next.add(c) : next.delete(c)))
  return next
}

/**
 * 按关键字过滤树：保留匹配节点及其祖先；匹配节点保留全部子孙。
 *
 * @param nodes - 树根节点列表
 * @param q - 关键字（名称 / 编码 / 路径，不区分大小写）
 * @returns 过滤后的新树
 */
export function filterTree(nodes: PermNode[], q: string): PermNode[] {
  const k = q.trim().toLowerCase()
  if (!k) return nodes
  const hit = (n: PermNode) =>
    [n.name, nodeLabel(n), n.code, n.path ?? ''].some((x) =>
      x.toLowerCase().includes(k)
    )
  return nodes.flatMap((n) => {
    if (hit(n)) return [n]
    const children = filterTree(n.children, q)
    return children.length ? [{ ...n, children }] : []
  })
}

/**
 * 收集树中全部节点 id（用于“全部展开”）。
 *
 * @param nodes - 树根节点列表
 * @returns 节点 id 列表
 */
export function allIds(nodes: PermNode[]): string[] {
  return nodes.flatMap((n) => [n.id, ...allIds(n.children)])
}
