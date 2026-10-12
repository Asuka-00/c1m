/** 头部通知铃铛：未读徽标 + 最新通知下拉，30 秒轮询。 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import { Bell } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { api, type Notification } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SeverityBadge } from './severity-badge'
import { linkTarget, noteTitle } from './utils'

/** 轮询间隔（毫秒）。 */
export const POLL_MS = 30_000

/** 通知铃铛：显示未读数，下拉列出最新通知，可全部标为已读、跳转消息中心。 */
export function NotificationBell() {
  const tenant = useAuthStore((s) => s.tenantId)
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
  const open = async (n: Notification) => {
    if (!n.is_read) await api.notifications.read([n.id]).then(refresh)
    if (n.link) void nav(linkTarget(n.link))
  }
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          variant='ghost'
          size='icon'
          className='relative rounded-full'
          aria-label={t('notify.bell')}
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
        </Button>
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
            <button
              key={n.id}
              type='button'
              onClick={() => open(n)}
              className={cn(
                'flex w-full flex-col gap-1 border-b px-3 py-2 text-start last:border-b-0 hover:bg-accent',
                !n.is_read && 'bg-primary/5'
              )}
            >
              <div className='flex items-center gap-2'>
                {!n.is_read && (
                  <span className='size-2 shrink-0 rounded-full bg-blue-600' />
                )}
                <SeverityBadge severity={n.severity} />
                <span className='ms-auto text-[11px] text-muted-foreground'>
                  {fmtDateTime(n.created_at)}
                </span>
              </div>
              <span className='line-clamp-2 text-sm'>{noteTitle(n)}</span>
            </button>
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
