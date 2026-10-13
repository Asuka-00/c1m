/** "以租户身份进入"提示：超级用户正在查看非成员租户时显示，可一键退出回到平台控制台。 */
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { t } from '@/i18n'
import { Eye, X } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

/** 工作区顶部栏中的模拟身份徽标。 */
export function ImpersonationBadge() {
  const imp = useAuthStore((s) => s.impersonating)
  const tenantId = useAuthStore((s) => s.tenantId)
  const setTenantId = useAuthStore((s) => s.setTenantId)
  const setImpersonating = useAuthStore((s) => s.setImpersonating)
  const qc = useQueryClient()
  const navigate = useNavigate()
  if (!imp || imp.id !== tenantId) return null
  return (
    <Badge
      variant='outline'
      data-testid='impersonation-badge'
      className='gap-1 border-amber-400 py-1 text-amber-700 dark:text-amber-300'
    >
      <Eye className='size-3' />
      {t('nav.impersonating', { name: imp.name })}
      <Button
        variant='ghost'
        size='icon'
        className='size-5'
        aria-label={t('nav.exitImpersonation')}
        title={t('nav.exitImpersonation')}
        onClick={() => {
          setImpersonating(null)
          setTenantId(null)
          qc.invalidateQueries()
          navigate({ to: '/$', params: { _splat: 'platform/tenants' } })
        }}
      >
        <X className='size-3' />
      </Button>
    </Badge>
  )
}
