/** 按菜单组件 key 渲染页面（动态页面与合并菜单页签共用）。 */
import { Suspense } from 'react'
import { Loader2 } from 'lucide-react'
import { MesEntityPage } from '@/features/mes/common/entity-page'
import { NotFoundError } from '@/features/shell/errors/not-found-error'
import { COMPONENTS } from './registry'

/** 加载中占位。 */
export const Spinner = () => (
  <div className='flex h-[50vh] items-center justify-center'>
    <Loader2 className='size-8 animate-spin text-muted-foreground' />
  </div>
)

/**
 * 渲染组件 key 对应的页面：`mes:<entity>` 为通用实体页，其余查注册表。
 *
 * @param component - 菜单组件 key
 * @returns 页面元素；未知 key 返回 404
 */
export function ComponentView({ component }: { component: string | null }) {
  if (component?.startsWith('mes:'))
    return <MesEntityPage key={component} code={component.slice(4)} />
  const Comp = component ? COMPONENTS[component] : undefined
  if (!Comp) return <NotFoundError />
  return (
    <Suspense fallback={<Spinner />}>
      <Comp key={component} />
    </Suspense>
  )
}
