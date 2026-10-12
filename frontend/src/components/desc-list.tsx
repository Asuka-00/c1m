import { cn } from '@/lib/utils'

/** 响应式描述列表：标签在值上方，列数自适应。 */
export function DescList({
  className,
  min = 180,
  children,
}: {
  className?: string
  min?: number
  children: React.ReactNode
}) {
  return (
    <dl
      className={cn('grid gap-x-6 gap-y-4 text-sm', className)}
      style={{
        gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))`,
      }}
      data-testid='desc-list'
    >
      {children}
    </dl>
  )
}

/** 单个信息项：弱化的标签、加粗的主值（最多换行 2 行）及
 *  可选的次要行（如编码对应的名称）。 */
export function DescItem({
  label,
  value,
  sub,
  className,
}: {
  label: React.ReactNode
  value: React.ReactNode
  sub?: React.ReactNode
  className?: string
}) {
  const tip = (x: React.ReactNode) =>
    typeof x === 'string' || typeof x === 'number' ? String(x) : undefined
  return (
    <div className={cn('min-w-0', className)} data-testid='desc-item'>
      <dt className='mb-0.5 text-xs font-medium text-muted-foreground'>
        {label}
      </dt>
      <dd
        className='line-clamp-2 font-medium break-words'
        title={tip(value)}
        data-fact
      >
        {value === '' || value == null ? '—' : value}
      </dd>
      {sub ? (
        <dd
          className='line-clamp-2 text-xs break-words text-muted-foreground'
          title={tip(sub)}
          data-fact
        >
          {sub}
        </dd>
      ) : null}
    </div>
  )
}

/** 带图标的居中空状态。 */
export function EmptyState({
  icon: Icon,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>
  children: React.ReactNode
}) {
  return (
    <div className='flex flex-col items-center gap-2 py-4 text-center text-sm text-muted-foreground'>
      <Icon className='size-6 opacity-60' />
      <p>{children}</p>
    </div>
  )
}
