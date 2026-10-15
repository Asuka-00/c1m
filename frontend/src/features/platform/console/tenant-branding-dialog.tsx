/** 平台控制台 · 租户品牌对话框：查看 / 编辑任意租户的品牌覆盖值。 */
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { api, type PlatformTenant } from '@/lib/api'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ConfigGroups } from '@/features/platform/config'

/**
 * 租户品牌（租户可覆盖的配置分组），保存走 /platform/tenants/{id}/branding。
 *
 * @param tenant 目标租户。
 * @param onClose 关闭回调。
 */
export function TenantBrandingDialog({
  tenant,
  onClose,
}: {
  tenant: PlatformTenant
  onClose: () => void
}) {
  const q = useQuery({
    queryKey: ['platform', 'branding', tenant.id],
    queryFn: () => api.platform.branding(tenant.id),
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[85vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {t('platform.brandingOf', { name: tenant.name })}
          </DialogTitle>
          <DialogDescription>{t('platform.brandingDesc')}</DialogDescription>
        </DialogHeader>
        <ConfigGroups
          loading={q.isLoading}
          groups={q.data?.data}
          scope='tenant'
          canEdit
          tenantId={tenant.id}
        />
      </DialogContent>
    </Dialog>
  )
}
