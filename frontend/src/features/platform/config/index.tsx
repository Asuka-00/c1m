/** 工作区 · 租户设置页面。 */
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Loader2 } from 'lucide-react'
import { api, type ConfigGroup } from '@/lib/api'
import { useCan, useCurrentTenant } from '@/lib/api/hooks'
import { Page } from '@/components/crud'
import { ConfigGroupCard } from './config-group-card'

/** 租户设置：当前租户在平台默认值之上的覆盖值（品牌等）。
 *  平台默认值已移至平台管理控制台（/platform/config）。 */
export default function ConfigPage() {
  const can = useCan()
  const current = useCurrentTenant()
  const q = useQuery({
    queryKey: ['config', 'tenant', current?.tenant.id],
    queryFn: api.config.tenant,
    enabled: !!current && can('config:read'),
  })
  return (
    <Page
      title={t('menu.config')}
      description={t('config.tenantDesc', {
        tenant: current?.tenant.name ?? '…',
      })}
    >
      <ConfigGroups
        loading={q.isLoading}
        groups={q.data?.data}
        scope='tenant'
        canEdit={can('config:write')}
      />
    </Page>
  )
}

/** 配置分组列表（加载中 / 空状态）。 */
export function ConfigGroups({
  loading,
  groups,
  scope,
  canEdit,
  tenantId,
}: {
  loading: boolean
  groups?: ConfigGroup[]
  scope: 'tenant' | 'platform'
  canEdit: boolean
  tenantId?: string
}) {
  if (loading) return <Loader2 className='mx-auto animate-spin' />
  return (
    <div className='flex flex-col gap-3'>
      {(groups ?? []).map((g) => (
        <ConfigGroupCard
          key={`${scope}-${tenantId ?? ''}-${g.code}`}
          group={g}
          scope={scope}
          canEdit={canEdit}
          tenantId={tenantId}
        />
      ))}
      {!groups?.length && (
        <p className='text-sm text-muted-foreground'>{t('config.empty')}</p>
      )}
    </div>
  )
}
