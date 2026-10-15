/** 首页生产概览：在制、Hold、Q-Time、设备状态、PM 到期、今日出站。 */
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { t } from '@/i18n'
import {
  Boxes,
  CalendarClock,
  LogOut,
  PauseCircle,
  Timer,
  Wrench,
} from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi } from '@/lib/api/mes/execution'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

/** 可点击跳转的指标卡片。 */
function Kpi({
  title,
  icon: Icon,
  to,
  children,
  tone,
}: {
  title: string
  icon: React.ElementType
  to: string
  children: React.ReactNode
  tone?: 'warn' | 'bad'
}) {
  return (
    <Link to='/$' params={{ _splat: to }} className='block'>
      <Card
        className={cn(
          'h-full transition-colors hover:bg-muted/50',
          tone === 'bad' && 'border-destructive/60',
          tone === 'warn' && 'border-amber-500/60'
        )}
      >
        <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
          <CardTitle className='text-sm font-medium'>{title}</CardTitle>
          <Icon className='size-4 text-muted-foreground' />
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </Link>
  )
}

/** 首页生产概览（需 mes.exec:read 权限，由调用方判断）。 */
export function HomeKpis() {
  const tk = useTenantKey()
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'home'],
    queryFn: execApi.home,
    refetchInterval: 60_000,
  })
  const d = q.data
  const big = 'text-2xl font-bold tabular-nums'
  const sub = 'text-xs text-muted-foreground'
  return (
    <div
      className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'
      data-testid='home-kpis'
    >
      <Kpi title={t('home.wip')} icon={Boxes} to='mes/wip-dashboard'>
        <div className={big}>{d?.wip_lots ?? '—'}</div>
        <p className={sub}>{t('home.wipQty', { n: d?.wip_qty ?? '—' })}</p>
      </Kpi>
      <Kpi
        title={t('home.hold')}
        icon={PauseCircle}
        to='mes/lot-hold'
        tone={d?.on_hold ? 'warn' : undefined}
      >
        <div className={big}>{d?.on_hold ?? '—'}</div>
        <p className={sub}>{t('home.holdHint')}</p>
      </Kpi>
      <Kpi
        title={t('home.qtime')}
        icon={Timer}
        to='mes/qtime-monitor'
        tone={d?.qtime_exceeded ? 'bad' : d?.qtime_warn ? 'warn' : undefined}
      >
        <div className={big}>
          <span className={d?.qtime_exceeded ? 'text-destructive' : ''}>
            {d?.qtime_exceeded ?? '—'}
          </span>
          <span className='mx-1 text-muted-foreground'>/</span>
          <span className={d?.qtime_warn ? 'text-amber-600' : ''}>
            {d?.qtime_warn ?? '—'}
          </span>
        </div>
        <p className={sub}>{t('home.qtimeHint')}</p>
      </Kpi>
      <Kpi title={t('home.equipment')} icon={Wrench} to='mes/eqp-board'>
        <div className='flex flex-wrap gap-3'>
          {(d?.equipment ?? []).map((e) => (
            <span
              key={e.category}
              className='inline-flex items-center gap-1.5 text-sm'
            >
              <span
                className='size-2.5 rounded-full'
                style={{ background: e.color ?? '#9ca3af' }}
              />
              <span className='font-mono'>{e.category}</span>
              <span className='font-semibold tabular-nums'>{e.count}</span>
            </span>
          ))}
          {!d?.equipment.length && <span className={sub}>—</span>}
        </div>
      </Kpi>
      <Kpi
        title={t('home.pm')}
        icon={CalendarClock}
        to='mes/eqp-board'
        tone={d?.pm_due ? 'bad' : d?.pm_warn ? 'warn' : undefined}
      >
        <div className={big}>
          <span className={d?.pm_due ? 'text-destructive' : ''}>
            {d?.pm_due ?? '—'}
          </span>
          <span className='mx-1 text-muted-foreground'>/</span>
          <span className={d?.pm_warn ? 'text-amber-600' : ''}>
            {d?.pm_warn ?? '—'}
          </span>
        </div>
        <p className={sub}>{t('home.pmHint')}</p>
      </Kpi>
      <Kpi title={t('home.trackOuts')} icon={LogOut} to='mes/lot-console'>
        <div className={big}>{d?.track_outs_today ?? '—'}</div>
        <p className={sub}>{t('home.trackOutsHint')}</p>
      </Kpi>
    </div>
  )
}
