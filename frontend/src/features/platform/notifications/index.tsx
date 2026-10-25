/** 消息中心页面：我的通知列表（搜索 / 类型 / 确认状态 / 严重度筛选），跳转关联对象，手动确认。 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import { Check, CheckCheck } from 'lucide-react'
import { api, type Notification } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  DataTable,
  Page,
  searchFilter,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { SeverityBadge } from '@/components/notify/severity-badge'
import { eventLabel, linkTarget, noteTitle } from '@/components/notify/utils'

/** 消息中心：分页列出当前用户的通知；跳转关联对象不改变状态，须手动确认。 */
export default function NotificationsPage() {
  const qc = useQueryClient()
  const filters: FilterDef[] = [
    searchFilter(t('notify.search')),
    {
      type: 'select',
      name: 'event_type',
      label: t('notify.allTypes'),
      optionsKey: ['notifications', 'event-types'],
      loadOptions: () =>
        api.notifications.meta().then((m) =>
          m.event_types.map((e) => ({
            value: e.code,
            label: eventLabel(e.code),
          }))
        ),
    },
    {
      type: 'select',
      name: 'is_read',
      label: t('notify.allRead'),
      options: [
        { value: 'false', label: t('notify.unread') },
        { value: 'true', label: t('notify.read') },
      ],
    },
    {
      type: 'select',
      name: 'severity',
      label: t('notify.allSeverities'),
      options: (['info', 'warning', 'critical'] as const).map((s) => ({
        value: s,
        label: t(`notify.severity.${s}`),
      })),
    },
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['notifications', 'page', lp.query],
    queryFn: () => api.notifications.list(lp.query),
  })
  const refresh = () => qc.invalidateQueries({ queryKey: ['notifications'] })
  const ack = (n: Notification) => api.notifications.read([n.id]).then(refresh)
  return (
    <Page
      title={t('notify.center')}
      description={t('notify.centerDesc')}
      actions={
        <Button
          variant='outline'
          onClick={() => api.notifications.read().then(refresh)}
        >
          <CheckCheck /> {t('notify.markAllRead')}
        </Button>
      }
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
            header: '',
            className: 'w-4',
            cell: (r) =>
              !r.is_read && (
                <span
                  className='block size-2 rounded-full bg-blue-600'
                  title={t('notify.unread')}
                />
              ),
          },
          {
            header: t('notify.time'),
            sortKey: 'created_at',
            cell: (r) => (
              <span className='whitespace-nowrap'>
                {fmtDateTime(r.created_at)}
              </span>
            ),
          },
          {
            header: t('notify.severityCol'),
            sortKey: 'severity',
            cell: (r) => <SeverityBadge severity={r.severity} />,
          },
          {
            header: t('notify.type'),
            sortKey: 'event_type',
            cell: (r) => eventLabel(r.event_type, r.event_label),
          },
          {
            header: t('notify.content'),
            cell: (r) => (
              <span className={cn(!r.is_read && 'font-medium')}>
                {noteTitle(r)}
              </span>
            ),
          },
          {
            header: t('notify.object'),
            cell: (r) =>
              r.link ? (
                <Link
                  {...linkTarget(r.link)}
                  className='font-mono text-xs text-blue-600 underline-offset-2 hover:underline'
                >
                  {r.object_code ?? t('notify.open')}
                </Link>
              ) : (
                (r.object_code ?? '')
              ),
          },
          {
            header: t('notify.readAt'),
            cell: (r) =>
              r.read_at ? (
                fmtDateTime(r.read_at)
              ) : (
                <IconButton
                  label={t('notify.ack')}
                  variant='outline'
                  onClick={() => ack(r)}
                >
                  <Check className='size-4' />
                </IconButton>
              ),
          },
        ]}
      />
    </Page>
  )
}
