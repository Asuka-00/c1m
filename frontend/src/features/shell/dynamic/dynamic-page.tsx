/** 动态页面：按后端菜单树解析并渲染组件。 */
import { Navigate, useSearch } from '@tanstack/react-router'
import type { MenuNode } from '@/lib/api'
import { useMyMenus } from '@/lib/api/hooks'
import { ForbiddenError } from '@/features/shell/errors/forbidden'
import { NotFoundError } from '@/features/shell/errors/not-found-error'
import { resolveRedirect } from './merged'
import { ComponentView, Spinner } from './render'
import { TabsPage } from './tabs-page'
import { TreePage } from './tree-page'

function flatten(nodes: MenuNode[]): MenuNode[] {
  return nodes.flatMap((n) => [n, ...flatten(n.children)])
}

/** 在后端菜单树中解析 `path` 并渲染对应组件。
 *  已并入合并菜单的旧路径 -> 重定向到对应页签；路径存在但无权限 -> 403；未知路径 -> 404。 */
export function DynamicPage({ path }: { path: string }) {
  const { data, isLoading } = useMyMenus()
  const search = useSearch({ strict: false }) as Record<string, unknown>
  if (isLoading || !data) return <Spinner />
  const node = flatten(data.menus).find((n) => n.path === path)
  if (!node) {
    const r = resolveRedirect(data.redirects, path, search)
    if (r)
      return (
        <Navigate
          to='/$'
          params={{ _splat: r.path.slice(1) }}
          search={r.search as never}
          replace
        />
      )
    return data.forbidden_paths.includes(path) ? (
      <ForbiddenError />
    ) : (
      <NotFoundError />
    )
  }
  if (node.component === 'tabs') return <TabsPage key={node.key} node={node} />
  if (node.component === 'tree') return <TreePage key={node.key} node={node} />
  return <ComponentView component={node.component} />
}
