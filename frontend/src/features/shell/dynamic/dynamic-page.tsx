/** 动态页面：按后端菜单树解析并渲染组件。 */
import { Suspense } from 'react'
import { Loader2 } from 'lucide-react'
import type { MenuNode } from '@/lib/api'
import { useMyMenus } from '@/lib/api/hooks'
import { MesEntityPage } from '@/features/mes/common/entity-page'
import { ForbiddenError } from '@/features/shell/errors/forbidden'
import { NotFoundError } from '@/features/shell/errors/not-found-error'
import { COMPONENTS } from './registry'

function flatten(nodes: MenuNode[]): MenuNode[] {
  return nodes.flatMap((n) => [n, ...flatten(n.children)])
}

const Spinner = () => (
  <div className='flex h-[50vh] items-center justify-center'>
    <Loader2 className='size-8 animate-spin text-muted-foreground' />
  </div>
)

/** 在后端菜单树中解析 `path` 并渲染对应组件。
 *  路径存在但无权限 -> 403；未知路径 -> 404。 */
export function DynamicPage({ path }: { path: string }) {
  const { data, isLoading } = useMyMenus()
  if (isLoading || !data) return <Spinner />
  const node = flatten(data.menus).find((n) => n.path === path)
  if (!node)
    return data.forbidden_paths.includes(path) ? (
      <ForbiddenError />
    ) : (
      <NotFoundError />
    )
  // MES 主数据：每个实体一个通用页面（组件 `mes:<entity>`）
  if (node.component?.startsWith('mes:'))
    return <MesEntityPage key={node.component} code={node.component.slice(4)} />
  const Comp = node.component ? COMPONENTS[node.component] : undefined
  if (!Comp) return <NotFoundError />
  return (
    <Suspense fallback={<Spinner />}>
      <Comp />
    </Suspense>
  )
}
