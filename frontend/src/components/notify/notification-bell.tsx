/** 头部通知铃铛：待确认徽标 + 待确认通知下拉（逐条或全部确认），30 秒轮询。 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import { Bell, Check } from 'lucide-react'
import { api, type Notification } from '@/lib/api'
import { useCurrentTenant } from '@/lib/api/hooks'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { IconButton } from '@/components/icon-button'
import { SeverityBadge } from './severity-badge'
import { linkTarget, noteTitle } from './utils'

/** 轮询间隔（毫秒）。 */
export const POLL_MS = 30_000

/** 通知铃铛：显示待确认数，下拉列出待确认通知；点击只跳转，须手动确认才消失。 */
export function NotificationBell() {
  const tenant = useCurrentTenant()?.tenant.id
  const qc = useQueryClient()
  const nav = useNavigate()
  const q = useQuery({
    queryKey: ['notifications', 'summary', tenant],
    queryFn: api.notifications.summary,
    enabled: !!tenant,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  })
  if (!tenant) return null
  const unread = q.data?.unread ?? 0
  const refresh = () => qc.invalidateQueries({ queryKey: ['notifications'] })
  const ack = (n: Notification) => api.notifications.read([n.id]).then(refresh)
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <IconButton
          label={t('notify.bell')}
          variant='ghost'
          className='relative rounded-full'
        >
          <Bell className='size-[1.2rem]' />
          {unread > 0 && (
            <span
              data-testid='notify-badge'
              className='absolute -end-0.5 -top-0.5 min-w-4 rounded-full bg-red-600 px-1 text-[10px] leading-4 font-semibold text-white'
            >
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </IconButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-96 p-0'>
        <div className='flex items-center justify-between border-b px-3 py-2'>
          <span className='text-sm font-semibold'>
            {t('notify.title')}
            {unread > 0 && (
              <span className='ms-1 font-normal text-muted-foreground'>
                ({t('notify.unreadCount', { count: unread })})
              </span>
            )}
          </span>
          <Button
            variant='link'
            size='sm'
            className='h-auto p-0'
            disabled={!unread}
            onClick={() => api.notifications.read().then(refresh)}
          >
            {t('notify.markAllRead')}
          </Button>
        </div>
        <div className='max-h-96 overflow-y-auto'>
          {(q.data?.latest ?? []).length === 0 && (
            <p className='p-6 text-center text-sm text-muted-foreground'>
              {t('notify.empty')}
            </p>
          )}
          {q.data?.latest.map((n) => (
            <div
              key={n.id}
              className='flex items-start gap-1 border-b bg-primary/5 last:border-b-0'
            >
              <button
                type='button'
                disabled={!n.link}
                onClick={() => n.link && void nav(linkTarget(n.link))}
                className={cn(
                  'flex min-w-0 flex-1 flex-col gap-1 px-3 py-2 text-start',
                  n.link && 'hover:bg-accent'
                )}
              >
                <div className='flex items-center gap-2'>
                  <SeverityBadge severity={n.severity} />
                  <span className='ms-auto text-[11px] text-muted-foreground'>
                    {fmtDateTime(n.created_at)}
                  </span>
                </div>
                <span className='line-clamp-2 text-sm'>{noteTitle(n)}</span>
              </button>
              <IconButton
                label={t('notify.ack')}
                variant='ghost'
                className='me-1 mt-1 shrink-0'
                onClick={() => ack(n)}
              >
                <Check className='size-4' />
              </IconButton>
            </div>
          ))}
        </div>
        <div className='border-t p-1'>
          <Button
            variant='ghost'
            size='sm'
            className='w-full'
            onClick={() =>
              nav({ to: '/$', params: { _splat: 'notifications' } })
            }
          >
            {t('notify.viewAll')}
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
