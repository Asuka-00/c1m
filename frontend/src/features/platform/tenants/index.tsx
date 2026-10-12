/** 租户管理页面。 */
import { useQuery } from '@tanstack/react-query'
import { fmtDate, t } from '@/i18n'
import { Plus } from 'lucide-react'
import { api, type Tenant } from '@/lib/api'
import { useApiMutation, useCan } from '@/lib/api/hooks'
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

/** 租户管理（平台管理员）：租户 CRUD 与启停。 */
export default function TenantsPage() {
  const can = useCan()
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
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['tenants', 'all', lp.query],
    queryFn: () => api.tenants.list(lp.query),
  })
  const s = useCrudState<Tenant>()
  const keys = [['tenants']]
  const create = useApiMutation(api.tenants.create, keys, t('tenants.created'))
  const update = useApiMutation(
    (b: { id: string; name: string; status?: string }) =>
      api.tenants.update(b.id, b),
    keys,
    t('tenants.updated')
  )
  const remove = useApiMutation(api.tenants.remove, keys, t('tenants.deleted'))
  const platform = can('tenants:write')
  return (
    <Page
      title={t('nav.tenants')}
      description={t('tenants.desc')}
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
            cell: (r) => <span className='font-medium'>{r.name}</span>,
          },
          {
            header: t('tenants.slug'),
            sortKey: 'slug',
            cell: (r) => <span className='font-mono text-xs'>{r.slug}</span>,
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
            header: t('common.created'),
            sortKey: 'created_at',
            cell: (r) => fmtDate(r.created_at),
          },
          {
            header: 'ID',
            cell: (r) => (
              <span className='font-mono text-xs text-muted-foreground'>
                {r.id.slice(0, 8)}
              </span>
            ),
          },
          {
            header: '',
            className: 'w-24',
            cell: (r) => (
              <RowActions
                onEdit={() => s.openEdit(r)}
                onDelete={
                  r.slug === 'default' ? undefined : () => s.openDelete(r)
                }
              />
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
            hidden: !s.editing || !platform,
            options: [
              { value: 'active', label: t('tenants.status.active') },
              { value: 'suspended', label: t('tenants.status.suspended') },
            ],
          },
        ]}
        initial={{
          name: s.editing?.name ?? '',
          slug: '',
          status: s.editing?.status ?? 'active',
        }}
        onSubmit={(v) =>
          s.editing
            ? update.mutateAsync({
                id: s.editing.id,
                name: v.name as string,
                ...(platform ? { status: v.status as string } : {}),
              })
            : create.mutateAsync({
                name: v.name as string,
                slug: v.slug as string,
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
    </Page>
  )
}
