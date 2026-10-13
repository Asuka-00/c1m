/** 首页。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Building2, KeyRound, TriangleAlert, Users } from 'lucide-react'
import { api } from '@/lib/api'
import {
  useCan,
  useCurrentTenant,
  useMe,
  useMyMenus,
  useMyTenants,
} from '@/lib/api/hooks'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Page } from '@/components/crud'
import { HomeKpis } from '@/features/mes/execution/home-kpis'

function Stat({
  title,
  value,
  icon: Icon,
  hint,
}: {
  title: string
  value: React.ReactNode
  icon: React.ElementType
  hint?: string
}) {
  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
        <CardTitle className='text-sm font-medium'>{title}</CardTitle>
        <Icon className='size-4 text-muted-foreground' />
      </CardHeader>
      <CardContent>
        <div className='text-2xl font-bold'>{value}</div>
        {hint && <p className='text-xs text-muted-foreground'>{hint}</p>}
      </CardContent>
    </Card>
  )
}

/** 首页仪表盘。 */
export default function Dashboard() {
  const { data: me } = useMe()
  const menus = useMyMenus('workspace')
  const tenants = useMyTenants()
  const current = useCurrentTenant()
  const can = useCan()
  // 权限码列表默认折叠（对业务用户意义不大）
  const [showPerms, setShowPerms] = useState(false)
  const members = useQuery({
    queryKey: ['members', current?.tenant.id, 'count'],
    queryFn: () => api.tenants.members(current!.tenant.id, { page_size: 1 }),
    enabled: can('members:read') && !!current,
  })
  return (
    <Page
      title={t('dashboard.title')}
      description={t('dashboard.signedInAs', { email: me?.username ?? '…' })}
    >
      {/* 未分配任何租户的普通用户：给出明确提示而不是报错 */}
      {tenants.data?.count === 0 && me && !me.is_superuser && (
        <Alert data-testid='no-tenant' className='mb-4'>
          <TriangleAlert />
          <AlertTitle>{t('dashboard.noTenantTitle')}</AlertTitle>
          <AlertDescription>{t('dashboard.noTenantDesc')}</AlertDescription>
        </Alert>
      )}
      {can('mes.exec:read') && current && <HomeKpis />}
      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
        <Stat
          title={t('dashboard.currentTenant')}
          value={current?.tenant.name ?? '—'}
          icon={Building2}
          hint={
            current
              ? t('dashboard.rolesHint', {
                  roles: current.roles.join(', ') || t('nav.noRole'),
                })
              : t('dashboard.selectTenant')
          }
        />
        <Stat
          title={t('menu.members')}
          value={members.data?.count ?? '—'}
          icon={Users}
          hint={t('dashboard.inTenant')}
        />
        <Stat
          title={t('dashboard.myTenants')}
          value={tenants.data?.count ?? '—'}
          icon={KeyRound}
          hint={me?.is_superuser ? t('dashboard.superuserHint') : undefined}
        />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t('dashboard.effective')}</CardTitle>
          <CardDescription>{t('dashboard.effectiveDesc')}</CardDescription>
          <CardAction>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => setShowPerms(!showPerms)}
              data-testid='toggle-perms'
            >
              {showPerms ? t('dashboard.hidePerms') : t('dashboard.showPerms')}
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className={showPerms ? 'flex flex-wrap gap-2' : 'hidden'}>
          {me?.is_superuser && <Badge>{t('dashboard.bypass')}</Badge>}
          {menus.data?.permissions.map((p) => (
            <Badge key={p} variant='secondary'>
              {p}
            </Badge>
          ))}
          {menus.data &&
            !menus.data.permissions.length &&
            !me?.is_superuser && (
              <span className='text-muted-foreground'>none</span>
            )}
        </CardContent>
      </Card>
    </Page>
  )
}
