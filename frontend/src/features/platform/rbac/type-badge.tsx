/** 权限类型徽标（MENU / BUTTON / API）。 */
import type { PermType } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'

const COLORS: Record<string, string> = {
  MENU: 'border-blue-300 bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  BUTTON:
    'border-amber-300 bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  API: 'border-violet-300 bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300',
}

/** 按类型着色的徽标。 */
export function TypeBadge({
  type,
  className,
}: {
  type: PermType
  className?: string
}) {
  return (
    <Badge
      variant='outline'
      className={cn(
        'px-1.5 py-0 font-mono text-[10px]',
        COLORS[type],
        className
      )}
    >
      {type}
    </Badge>
  )
}
