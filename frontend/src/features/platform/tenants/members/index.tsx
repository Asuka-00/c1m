/** 租户成员页面。 */
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { UserPlus } from 'lucide-react'
import { ALL, api, type Member } from '@/lib/api'
import {
  useApiMutation,
  useCan,
  useCurrentTenant,
  useMe,
} from '@/lib/api/hooks'
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

/** 租户成员管理：添加成员、分配租户角色、移除成员。 */
export default function MembersPage() {
  const can = useCan()
  const { data: me } = useMe()
  const current = useCurrentTenant()
  const tid = current?.tenant.id
  const filters: FilterDef[] = [
    searchFilter(t('table.searchUsers')),
    {
      type: 'select',
      name: 'role_id',
      label: t('table.allRoles'),
      optionsKey: ['tenant-roles', tid, 'options'],
      loadOptions: () =>
        tid
          ? api.tenants
              .roles(tid, ALL)
              .then((r) => r.data.map((x) => ({ value: x.id, label: x.name })))
          : Promise.resolve([]),
    },
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['members', tid, lp.query],
    queryFn: () => api.tenants.members(tid!, lp.query),
    enabled: !!tid,
  })
  const roles = useQuery({
    queryKey: ['tenant-roles', tid, 'all'],
    queryFn: () => api.tenants.roles(tid!, ALL),
    enabled: !!tid,
  })
  const roleOptions =
    roles.data?.data.map((r) => ({ value: r.name, label: r.name })) ?? []
  const s = useCrudState<Member>()
  const keys = [['members'], ['tenants', 'me'], ['menus']]
  const add = useApiMutation(
    (b: { email: string; roles: string[] }) => api.tenants.addMember(tid!, b),
    keys,
    t('members.added')
  )
  const setRoles = useApiMutation(
    (b: { user_id: string; roles: string[] }) =>
      api.tenants.setMemberRoles(tid!, b.user_id, b.roles),
    keys,
    t('members.rolesUpdated')
  )
  const remove = useApiMutation(
    (uid: string) => api.tenants.removeMember(tid!, uid),
    keys,
    t('members.removed')
  )
  const writable = can('members:write')
  return (
    <Page
      title={t('menu.members')}
      description={t('members.desc', { tenant: current?.tenant.name ?? '…' })}
      actions={
        writable && (
          <Button onClick={s.openCreate}>
            <UserPlus /> {t('members.add')}
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
        rowKey={(r) => r.user_id}
        columns={[
          {
            header: t('common.email'),
            sortKey: 'email',
            cell: (r) => (
              <span className='font-medium'>
                {r.email}
                {r.user_id === me?.id && (
                  <span className='ms-1 text-muted-foreground'>
                    {t('common.you')}
                  </span>
                )}
              </span>
            ),
          },
          {
            header: t('common.name'),
            sortKey: 'full_name',
            cell: (r) => r.full_name ?? '—',
          },
          {
            header: t('common.roles'),
            cell: (r) => (
              <div className='flex gap-1'>
                {r.roles.map((x) => (
                  <Badge
                    key={x}
                    variant={x === 'owner' ? 'default' : 'secondary'}
                  >
                    {x}
                  </Badge>
                ))}
                {!r.roles.length && '—'}
              </div>
            ),
          },
          {
            header: '',
            className: 'w-24',
            cell: (r) => (
              <RowActions
                onEdit={writable ? () => s.openEdit(r) : undefined}
                onDelete={
                  writable || r.user_id === me?.id
                    ? () => s.openDelete(r)
                    : undefined
                }
              />
            ),
          },
        ]}
      />
      <FormDialog
        open={s.formOpen}
        onOpenChange={(o) => !o && s.closeForm()}
        title={
          s.editing
            ? t('members.rolesOf', { email: s.editing.email })
            : t('members.add')
        }
        description={s.editing ? undefined : t('members.addDesc')}
        fields={[
          {
            name: 'email',
            label: t('common.email'),
            type: 'email',
            required: true,
            hidden: !!s.editing,
          },
          {
            name: 'roles',
            label: t('roles.tenantTitle'),
            type: 'multi',
            options: roleOptions,
          },
        ]}
        initial={{ email: '', roles: s.editing?.roles ?? ['member'] }}
        onSubmit={(v) =>
          s.editing
            ? setRoles.mutateAsync({
                user_id: s.editing.user_id,
                roles: v.roles as string[],
              })
            : add.mutateAsync({
                email: v.email as string,
                roles: v.roles as string[],
              })
        }
      />
      <ConfirmDialog
        open={!!s.deleting}
        onOpenChange={(o) => !o && s.closeDelete()}
        title={
          s.deleting?.user_id === me?.id
            ? t('members.leave')
            : t('members.remove')
        }
        desc={`Remove ${s.deleting?.email} from ${current?.tenant.name}?`}
        destructive
        confirmText={t('common.remove')}
        handleConfirm={() =>
          s.deleting &&
          remove.mutate(s.deleting.user_id, { onSuccess: s.closeDelete })
        }
      />
    </Page>
  )
}
