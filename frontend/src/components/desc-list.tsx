import { cn } from '@/lib/utils'

/** Responsive description list: labels above values, auto-fit columns. */
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

/** One fact: muted label, bold primary value (may wrap to 2 lines) and an
 *  optional secondary line (e.g. the name behind a code). */
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

/** Centered empty state with icon. */
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
