/** 平台控制台 · 平台操作日志：超级用户的平台写操作、跨租户读取与"以租户身份进入"。 */
import { useQuery } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { api } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import {
  DataTable,
  Page,
  searchFilter,
  useListParams,
  type FilterDef,
} from '@/components/crud'

/** 已知的平台操作。 */
const ACTIONS = [
  'tenant.create',
  'tenant.update',
  'tenant.delete',
  'tenant.enter',
  'tenant.exit',
  'tenant.owner',
  'tenant.branding',
  'member.add',
  'member.roles',
  'member.remove',
  'config.update',
  'channel.update',
  'audit.cross_tenant_read',
]

export default function PlatformOpsLogPage() {
  const filters: FilterDef[] = [
    searchFilter(t('platform.searchOps')),
    {
      type: 'select',
      name: 'action',
      label: t('platform.allActions'),
      options: ACTIONS.map((a) => ({
        value: a,
        label: t(`platform.actions.${a}`, { defaultValue: a }),
      })),
    },
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['platform', 'ops-log', lp.query],
    queryFn: () => api.platform.opsLog(lp.query),
  })
  return (
    <Page title={t('menu.p-ops-log')} description={t('platform.opsLogDesc')}>
      <DataTable
        rows={q.data?.data}
        total={q.data?.count}
        params={lp}
        filters={filters}
        loading={q.isLoading}
        rowKey={(r) => r.id}
        columns={[
          {
            header: t('platform.time'),
            sortKey: 'created_at',
            cell: (r) => fmtDateTime(r.created_at),
          },
          {
            header: t('platform.actor'),
            cell: (r) => <span className='font-medium'>{r.actor_email}</span>,
          },
          {
            header: t('platform.action'),
            sortKey: 'action',
            cell: (r) => (
              <Badge
                variant={r.action === 'tenant.enter' ? 'default' : 'outline'}
              >
                {t(`platform.actions.${r.action}`, { defaultValue: r.action })}
              </Badge>
            ),
          },
          {
            header: t('platform.target'),
            cell: (r) => (
              <span className='font-mono text-xs'>
                {r.target_type}
                {r.target_id ? ` · ${r.target_id.slice(0, 36)}` : ''}
              </span>
            ),
          },
          {
            header: t('platform.detail'),
            cell: (r) => (
              <span className='block max-w-72 truncate font-mono text-xs text-muted-foreground'>
                {r.detail ? JSON.stringify(r.detail) : '—'}
              </span>
            ),
          },
        ]}
      />
    </Page>
  )
}
