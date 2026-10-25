/** 批次操作台侧栏卡片标题：标题单行，操作按钮另起一行等宽铺满，放不下时整行换行。 */
import type { ComponentType, ReactNode } from 'react'
import { CardHeader, CardTitle } from '@/components/ui/card'

export function SideCardHeader({
  icon: Icon,
  title,
  children,
}: {
  icon: ComponentType<{ className?: string }>
  title: string
  children?: ReactNode
}) {
  return (
    <CardHeader className='flex flex-col gap-3'>
      <CardTitle className='flex w-full min-w-0 items-center gap-2 text-base'>
        <Icon className='size-4 shrink-0 text-muted-foreground' />
        <span className='truncate whitespace-nowrap'>{title}</span>
      </CardTitle>
      {children && (
        <div className='flex w-full flex-wrap gap-2 *:flex-1'>{children}</div>
      )}
    </CardHeader>
  )
}
