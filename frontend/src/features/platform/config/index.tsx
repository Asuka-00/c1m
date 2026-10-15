/** 系统配置页面。 */
import { useState } from 'react'
import { AxiosError } from 'axios'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { useCan, useCurrentTenant, useMe } from '@/lib/api/hooks'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page } from '@/components/crud'
import { ConfigGroupCard } from './config-group-card'

type Scope = 'tenant' | 'platform'

/** 系统配置：当前租户的设置（在平台值之上的覆盖值），
 *  平台管理员还可编辑平台默认值。 */
export default function ConfigPage() {
  const can = useCan()
  const current = useCurrentTenant()
  const { data: me } = useMe()
  const tenantQ = useQuery({
    queryKey: ['config', 'tenant', current?.tenant.id],
    queryFn: api.config.tenant,
    enabled: !!current && can('config:read'),
  })
  // 平台默认值：仅当平台接口允许（拥有平台角色）时显示
  const platformQ = useQuery({
    queryKey: ['config', 'platform'],
    queryFn: api.config.platform,
    retry: (n, e) =>
      !(e instanceof AxiosError && e.response?.status === 403) && n < 2,
  })
  const hasPlatform = platformQ.isSuccess
  const hasTenant = !!current && can('config:read')
  const [tab, setTab] = useState<Scope>(hasTenant ? 'tenant' : 'platform')
  const scope: Scope = !hasTenant ? 'platform' : !hasPlatform ? 'tenant' : tab
  const q = scope === 'tenant' ? tenantQ : platformQ
  const canEdit =
    scope === 'tenant'
      ? can('config:write')
      : !!me && hasPlatform && can('config:write')

  return (
    <Page
      title={t('config.title')}
      description={
        scope === 'tenant'
          ? t('config.tenantDesc', { tenant: current?.tenant.name ?? '…' })
          : t('config.platformDesc')
      }
    >
      {hasTenant && hasPlatform && (
        <Tabs
          value={scope}
          onValueChange={(v) => setTab(v as Scope)}
          className='mb-4'
        >
          <TabsList>
            <TabsTrigger value='tenant'>
              {t('config.tenantTab', { tenant: current?.tenant.name ?? '' })}
            </TabsTrigger>
            <TabsTrigger value='platform'>
              {t('config.platformTab')}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      )}
      {q.isLoading ? (
        <Loader2 className='mx-auto animate-spin' />
      ) : (
        <div className='flex flex-col gap-3'>
          {(q.data?.data ?? []).map((g) => (
            <ConfigGroupCard
              key={`${scope}-${g.code}`}
              group={g}
              scope={scope}
              canEdit={canEdit}
            />
          ))}
          {!q.data?.data.length && (
            <p className='text-sm text-muted-foreground'>{t('config.empty')}</p>
          )}
        </div>
      )}
    </Page>
  )
}
