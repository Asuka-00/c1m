/** 通知严重度徽标。 */
import { t } from '@/i18n'
import type { Severity } from '@/lib/api'
import { cn } from '@/lib/utils'
import { SEVERITY_CLASS } from './utils'

/** 显示本地化严重度的彩色徽标。 */
export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={cn(
        'inline-flex rounded px-1.5 py-0.5 text-[11px] font-medium',
        SEVERITY_CLASS[severity]
      )}
    >
      {t(`notify.severity.${severity}`)}
    </span>
  )
}
