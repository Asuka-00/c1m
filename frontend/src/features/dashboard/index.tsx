import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Building2, KeyRound, Users } from 'lucide-react'
import { api } from '@/lib/api'
import {
  useCan,
  useCurrentTenant,
  useMe,
  useMyMenus,
  useMyTenants,
} from '@/lib/api/hooks'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Page } from '@/components/crud'

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

export default function Dashboard() {
  const { data: me } = useMe()
  const menus = useMyMenus()
  const tenants = useMyTenants()
  const current = useCurrentTenant()
  const can = useCan()
  const members = useQuery({
    queryKey: ['members', current?.tenant.id, 'count'],
    queryFn: () => api.tenants.members(current!.tenant.id, { page_size: 1 }),
    enabled: can('members:read') && !!current,
  })
  return (
    <Page
      title={t('dashboard.title')}
      description={t('dashboard.signedInAs', { email: me?.email ?? '…' })}
    >
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
        </CardHeader>
        <CardContent className='flex flex-wrap gap-2'>
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
