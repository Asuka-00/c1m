/** 角色管理组件（平台 / 租户共用）。 */
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Plus } from 'lucide-react'
import { api, type Role } from '@/lib/api'
import { useApiMutation, useCan, useCurrentTenant } from '@/lib/api/hooks'
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

/** 平台角色（/roles）或租户角色（/tenants/{id}/roles）的 CRUD。 */
export function RolesManager({ scope }: { scope: 'platform' | 'tenant' }) {
  const can = useCan()
  const current = useCurrentTenant()
  const tid = current?.tenant.id
  const filters: FilterDef[] = [searchFilter(t('table.searchRoles'))]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey:
      scope === 'platform'
        ? ['roles', lp.query]
        : ['tenant-roles', tid, lp.query],
    queryFn: () =>
      scope === 'platform'
        ? api.roles.list(lp.query)
        : api.tenants.roles(tid!, lp.query),
    enabled: scope === 'platform' || !!tid,
  })
  const writable =
    scope === 'platform' ? can('roles:write') : can('tenant:manage')
  const keys = [['roles'], ['tenant-roles']]
  const s = useCrudState<Role>()
  const create = useApiMutation(
    (b: { name: string; description: string }) =>
      scope === 'platform'
        ? api.roles.create(b)
        : api.tenants.createRole(tid!, b),
    keys,
    t('roles.created')
  )
  const update = useApiMutation(
    (b: { id: string; name: string; description: string }) =>
      scope === 'platform'
        ? api.roles.update(b.id, b)
        : api.tenants.updateRole(tid!, b.id, b),
    keys,
    t('roles.updated')
  )
  const remove = useApiMutation(
    (id: string) =>
      scope === 'platform'
        ? api.roles.remove(id)
        : api.tenants.removeRole(tid!, id),
    keys,
    t('roles.deleted')
  )
  const builtin = (r: Role) =>
    (scope === 'platform' ? ['admin', 'user'] : ['owner']).includes(r.name)
  return (
    <Page
      title={scope === 'platform' ? t('common.roles') : t('roles.tenantTitle')}
      description={
        scope === 'platform'
          ? t('roles.platformDesc')
          : t('roles.tenantDesc', { tenant: current?.tenant.name ?? '…' })
      }
      actions={
        writable && (
          <Button onClick={s.openCreate}>
            <Plus /> {t('roles.new')}
          </Button>
        )
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
            header: t('common.description'),
            sortKey: 'description',
            cell: (r) => r.description ?? '',
          },
          {
            header: t('common.permissions'),
            cell: (r) => (
              <div className='flex max-w-xl flex-wrap gap-1'>
                {r.permissions.map((p) => (
                  <Badge
                    key={p.id}
                    variant='secondary'
                    className='font-mono text-[10px]'
                  >
                    {p.code}
                  </Badge>
                ))}
              </div>
            ),
          },
          {
            header: '',
            className: 'w-24',
            cell: (r) =>
              writable && (
                <RowActions
                  onEdit={() => s.openEdit(r)}
                  onDelete={builtin(r) ? undefined : () => s.openDelete(r)}
                />
              ),
          },
        ]}
      />
      <FormDialog
        open={s.formOpen}
        onOpenChange={(o) => !o && s.closeForm()}
        title={s.editing ? t('roles.edit') : t('roles.new')}
        fields={[
          { name: 'name', label: t('common.name'), required: true },
          { name: 'description', label: t('common.description') },
        ]}
        initial={{
          name: s.editing?.name ?? '',
          description: s.editing?.description ?? '',
        }}
        onSubmit={(v) => {
          const b = {
            name: v.name as string,
            description: v.description as string,
          }
          return s.editing
            ? update.mutateAsync({ id: s.editing.id, ...b })
            : create.mutateAsync(b)
        }}
      />
      <ConfirmDialog
        open={!!s.deleting}
        onOpenChange={(o) => !o && s.closeDelete()}
        title={t('roles.delete')}
        desc={t('roles.deleteDesc', { name: s.deleting?.name })}
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
