/** 动态页面：按后端菜单树解析并渲染组件。 */
import type { MenuNode } from '@/lib/api'
import { useMyMenus } from '@/lib/api/hooks'
import { isPlatformPath } from '@/lib/space'
import { ForbiddenError } from '@/features/shell/errors/forbidden'
import { NotFoundError } from '@/features/shell/errors/not-found-error'
import { ComponentView, Spinner } from './render'
import { TabsPage } from './tabs-page'
import { TreePage } from './tree-page'

function flatten(nodes: MenuNode[]): MenuNode[] {
  return nodes.flatMap((n) => [n, ...flatten(n.children)])
}

/** 在后端菜单树中解析 `path` 并渲染对应组件。
 *  路径存在但无权限 -> 403；未知路径 -> 404。 */
export function DynamicPage({ path }: { path: string }) {
  const { data, isLoading, isError } = useMyMenus()
  // 平台控制台菜单仅超级用户可取（其他用户 403）
  if (isError && isPlatformPath(path)) return <ForbiddenError inApp />
  if (isLoading || !data) return <Spinner />
  const node = flatten(data.menus).find((n) => n.path === path)
  if (!node) {
    return data.forbidden_paths.includes(path) ? (
      <ForbiddenError inApp />
    ) : (
      <NotFoundError />
    )
  }
  if (node.component === 'tabs') return <TabsPage key={node.key} node={node} />
  if (node.component === 'tree') return <TreePage key={node.key} node={node} />
  return <ComponentView component={node.component} />
}
