/** 平台控制台 · 跨租户审计日志：逐租户读取业务审计（RLS 显式切换，读取本身记入平台操作日志）。 */
import { useQuery } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { ALL, api } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import {
  DataTable,
  Page,
  searchFilter,
  useListParams,
  type FilterDef,
} from '@/components/crud'

export default function PlatformAuditPage() {
  const filters: FilterDef[] = [
    searchFilter(t('platform.searchAudit')),
    {
      type: 'select',
      name: 'tenant_id',
      label: t('platform.allTenants'),
      optionsKey: ['platform', 'tenants', 'options'],
      loadOptions: () =>
        api.platform
          .tenants(ALL)
          .then((r) => r.data.map((x) => ({ value: x.id, label: x.name }))),
    },
    {
      type: 'select',
      name: 'action',
      label: t('platform.allActions'),
      options: ['create', 'update', 'delete'].map((a) => ({
        value: a,
        label: t(`mes.enum.audit_action.${a}`, { defaultValue: a }),
      })),
    },
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['platform', 'audit', lp.query],
    queryFn: () => api.platform.audit(lp.query),
  })
  return (
    <Page title={t('menu.p-audit')} description={t('platform.auditDesc')}>
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
            cell: (r) => fmtDateTime(r.created_at),
          },
          {
            header: t('platform.tenant'),
            cell: (r) => <Badge variant='outline'>{r.tenant_name}</Badge>,
          },
          {
            header: t('platform.entity'),
            cell: (r) =>
              r.entity_type
                ? t(`mes.entity.${r.entity_type}`, {
                    defaultValue: r.entity_type,
                  })
                : '—',
          },
          {
            header: t('platform.action'),
            cell: (r) =>
              r.action
                ? t(`mes.enum.audit_action.${r.action}`, {
                    defaultValue: r.action,
                  })
                : '—',
          },
          { header: t('platform.record'), cell: (r) => r.record_code ?? '—' },
          { header: t('platform.actor'), cell: (r) => r.user_email ?? '—' },
        ]}
      />
    </Page>
  )
}
