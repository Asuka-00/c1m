/** 平台控制台 · 登录日志：所有登录尝试（成功 / 失败），分页、搜索、筛选。 */
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

export default function LoginLogPage() {
  const filters: FilterDef[] = [
    searchFilter(t('platform.searchLogin')),
    {
      type: 'select',
      name: 'success',
      label: t('platform.allResults'),
      options: [
        { value: 'true', label: t('platform.success') },
        { value: 'false', label: t('platform.failure') },
      ],
    },
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['platform', 'login-log', lp.query],
    queryFn: () => api.platform.loginLog(lp.query),
  })
  return (
    <Page
      title={t('menu.p-login-log')}
      description={t('platform.loginLogDesc')}
    >
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
            header: t('common.loginName'),
            sortKey: 'username',
            cell: (r) => <span className='font-medium'>{r.username}</span>,
          },
          {
            header: t('platform.result'),
            cell: (r) => (
              <Badge variant={r.success ? 'secondary' : 'destructive'}>
                {r.success ? t('platform.success') : t('platform.failure')}
              </Badge>
            ),
          },
          {
            header: t('platform.reason'),
            cell: (r) =>
              r.reason
                ? t(`platform.reasons.${r.reason}`, { defaultValue: r.reason })
                : '—',
          },
          { header: 'IP', cell: (r) => r.ip ?? '—' },
          {
            header: t('platform.userAgent'),
            cell: (r) => (
              <span
                className='block max-w-64 truncate text-xs text-muted-foreground'
                title={r.user_agent ?? ''}
              >
                {r.user_agent ?? '—'}
              </span>
            ),
          },
        ]}
      />
    </Page>
  )
}
