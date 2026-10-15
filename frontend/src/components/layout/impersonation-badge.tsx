/** "以租户身份进入"提示：平台管理员以租户身份进入（短期模拟令牌）时显示，可一键退出回到平台控制台。 */
import { t } from '@/i18n'
import { Eye, X } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { Badge } from '@/components/ui/badge'
import { IconButton } from '@/components/icon-button'
import { useExitTenant } from '@/features/platform/console/enter-tenant'

/** 工作区顶部栏中的模拟身份徽标。 */
export function ImpersonationBadge() {
  const imp = useAuthStore((s) => s.impersonating)
  const tenantId = useAuthStore((s) => s.tenantId)
  const exit = useExitTenant()
  if (!imp || imp.id !== tenantId) return null
  return (
    <Badge
      variant='outline'
      data-testid='impersonation-badge'
      className='gap-1 border-amber-400 py-1 text-amber-700 dark:text-amber-300'
    >
      <Eye className='size-3' />
      {t('nav.impersonating', { name: imp.name })}
      <IconButton
        label={t('nav.exitImpersonation')}
        variant='ghost'
        className='size-5'
        onClick={exit}
      >
        <X className='size-3' />
      </IconButton>
    </Badge>
  )
}
