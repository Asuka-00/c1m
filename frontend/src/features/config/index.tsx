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

/** System configuration: the current tenant's settings (overrides on top of the
 *  platform values) and, for platform admins, the platform defaults. */
export default function ConfigPage() {
  const can = useCan()
  const current = useCurrentTenant()
  const { data: me } = useMe()
  const tenantQ = useQuery({
    queryKey: ['config', 'tenant', current?.tenant.id],
    queryFn: api.config.tenant,
    enabled: !!current && can('config:read'),
  })
  // platform defaults: visible iff the platform endpoint allows us (platform role)
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
