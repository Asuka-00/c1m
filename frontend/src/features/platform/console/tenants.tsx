/** 平台控制台 · 租户列表：创建 / 停用 / 套餐 / 到期、成员与 owner、品牌、以租户身份进入。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fmtDate, t } from '@/i18n'
import { LogIn, Palette, Plus, Users } from 'lucide-react'
import { api, type PlatformTenant } from '@/lib/api'
import { useApiMutation } from '@/lib/api/hooks'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  ConfirmDialog,
  DataTable,
  FormDialog,
  Page,
  RowActions,
  useCrudState,
  useListParams,
  type FilterDef,
  searchFilter,
} from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { useEnterTenant } from './enter-tenant'
import { TenantBrandingDialog } from './tenant-branding-dialog'
import { TenantMembersDialog } from './tenant-members-dialog'

const PLANS = ['trial', 'standard', 'enterprise'] as const

/** 到期日：YYYY-MM-DD（本地）<-> ISO；空表示永久。 */
const toDay = (iso: string | null) => (iso ? iso.slice(0, 10) : '')
const fromDay = (d: string) =>
  d.trim() ? new Date(`${d.trim()}T23:59:59`).toISOString() : null
const expired = (iso: string | null) => !!iso && new Date(iso) < new Date()

/** 租户管理（平台）。 */
export default function PlatformTenantsPage() {
  const planOpts = PLANS.map((p) => ({
    value: p,
    label: t(`platform.plans.${p}`),
  }))
  const filters: FilterDef[] = [
    searchFilter(t('table.searchTenants')),
    {
      type: 'select',
      name: 'status',
      label: t('table.allStatuses'),
      options: [
        { value: 'active', label: t('tenants.status.active') },
        { value: 'suspended', label: t('tenants.status.suspended') },
      ],
    },
    {
      type: 'select',
      name: 'plan',
      label: t('platform.allPlans'),
      options: planOpts,
    },
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['platform', 'tenants', lp.query],
    queryFn: () => api.platform.tenants(lp.query),
  })
  const s = useCrudState<PlatformTenant>()
  const [members, setMembers] = useState<PlatformTenant | null>(null)
  const [branding, setBranding] = useState<PlatformTenant | null>(null)
  const enter = useEnterTenant()
  const keys = [['platform', 'tenants'], ['tenants']]
  const create = useApiMutation(
    api.platform.createTenant,
    keys,
    t('tenants.created')
  )
  const update = useApiMutation(
    (b: { id: string } & Parameters<typeof api.platform.updateTenant>[1]) =>
      api.platform.updateTenant(b.id, b),
    keys,
    t('tenants.updated')
  )
  const remove = useApiMutation(
    api.platform.removeTenant,
    keys,
    t('tenants.deleted')
  )
  return (
    <Page
      title={t('menu.p-tenants')}
      description={t('platform.tenantsDesc')}
      actions={
        <Button onClick={s.openCreate}>
          <Plus /> {t('tenants.new')}
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
            header: t('common.name'),
            sortKey: 'name',
            cell: (r) => (
              <div>
                <div className='font-medium'>{r.name}</div>
                <div className='font-mono text-xs text-muted-foreground'>
                  {r.slug}
                </div>
              </div>
            ),
          },
          {
            header: t('common.status'),
            sortKey: 'status',
            cell: (r) => (
              <Badge
                variant={r.status === 'active' ? 'secondary' : 'destructive'}
              >
                {t(`tenants.status.${r.status}`, { defaultValue: r.status })}
              </Badge>
            ),
          },
          {
            header: t('platform.plan'),
            sortKey: 'plan',
            cell: (r) =>
              t(`platform.plans.${r.plan}`, { defaultValue: r.plan }),
          },
          {
            header: t('platform.expiresAt'),
            sortKey: 'expires_at',
            cell: (r) =>
              r.expires_at ? (
                <span
                  className={expired(r.expires_at) ? 'text-destructive' : ''}
                >
                  {fmtDate(r.expires_at)}
                  {expired(r.expires_at) && ` · ${t('platform.expired')}`}
                </span>
              ) : (
                <span className='text-muted-foreground'>
                  {t('platform.never')}
                </span>
              ),
          },
          {
            header: t('platform.owners'),
            cell: (r) => (
              <span className='text-xs'>{r.owners.join(', ') || '—'}</span>
            ),
          },
          {
            header: t('platform.memberCount'),
            cell: (r) => r.member_count,
          },
          {
            header: t('common.created'),
            sortKey: 'created_at',
            cell: (r) => fmtDate(r.created_at),
          },
          {
            header: '',
            className: 'w-56',
            cell: (r) => (
              <RowActions
                onEdit={() => s.openEdit(r)}
                onDelete={
                  r.slug === 'default' ? undefined : () => s.openDelete(r)
                }
              >
                <IconButton
                  label={t('platform.members')}
                  variant='ghost'
                  onClick={() => setMembers(r)}
                >
                  <Users className='size-4' />
                </IconButton>
                <IconButton
                  label={t('platform.branding')}
                  variant='ghost'
                  onClick={() => setBranding(r)}
                >
                  <Palette className='size-4' />
                </IconButton>
                <IconButton
                  label={t('platform.enter')}
                  variant='ghost'
                  data-testid={`enter-${r.slug}`}
                  onClick={() => enter(r)}
                >
                  <LogIn className='size-4' />
                </IconButton>
              </RowActions>
            ),
          },
        ]}
      />
      <FormDialog
        open={s.formOpen}
        onOpenChange={(o) => !o && s.closeForm()}
        title={s.editing ? t('tenants.edit') : t('tenants.new')}
        fields={[
          { name: 'name', label: t('common.name'), required: true },
          {
            name: 'slug',
            label: t('tenants.slugLabel'),
            required: true,
            hidden: !!s.editing,
          },
          {
            name: 'status',
            label: t('common.status'),
            type: 'select',
            hidden: !s.editing,
            options: [
              { value: 'active', label: t('tenants.status.active') },
              { value: 'suspended', label: t('tenants.status.suspended') },
            ],
          },
          {
            name: 'plan',
            label: t('platform.plan'),
            type: 'select',
            options: planOpts,
          },
          {
            name: 'expires_at',
            label: t('platform.expiresAt'),
            placeholder: t('platform.expiresHint'),
          },
          {
            name: 'owner',
            label: t('platform.ownerUsername'),
            hidden: !!s.editing,
          },
        ]}
        initial={{
          name: s.editing?.name ?? '',
          slug: '',
          status: s.editing?.status ?? 'active',
          plan: s.editing?.plan ?? 'standard',
          expires_at: toDay(s.editing?.expires_at ?? null),
          owner: '',
        }}
        onSubmit={(v) =>
          s.editing
            ? update.mutateAsync({
                id: s.editing.id,
                name: v.name as string,
                status: v.status as string,
                plan: v.plan as string,
                expires_at: fromDay(v.expires_at as string),
              })
            : create.mutateAsync({
                name: v.name as string,
                slug: v.slug as string,
                plan: v.plan as string,
                expires_at: fromDay(v.expires_at as string),
                owner: ((v.owner as string) || '').trim() || null,
              })
        }
      />
      <ConfirmDialog
        open={!!s.deleting}
        onOpenChange={(o) => !o && s.closeDelete()}
        title={t('tenants.delete')}
        desc={t('tenants.deleteDesc', { name: s.deleting?.name })}
        destructive
        confirmText={t('common.delete')}
        handleConfirm={() =>
          s.deleting &&
          remove.mutate(s.deleting.id, { onSuccess: s.closeDelete })
        }
      />
      {members && (
        <TenantMembersDialog
          tenant={members}
          onClose={() => setMembers(null)}
        />
      )}
      {branding && (
        <TenantBrandingDialog
          tenant={branding}
          onClose={() => setBranding(null)}
        />
      )}
    </Page>
  )
}
