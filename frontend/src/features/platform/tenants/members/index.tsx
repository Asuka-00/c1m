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
import { roleLabel } from '@/lib/rbac-labels'
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
} from '@/components/crud'
import { StatusBadge } from '../../rbac/status'

/** 租户成员（用户与权限 · 用户）：按用户名 / 显示名 / 状态 / 角色筛选，
 *  标签多选分配租户角色，添加与移除成员。 */
export default function MembersPage() {
  const can = useCan()
  const { data: me } = useMe()
  const current = useCurrentTenant()
  const tid = current?.tenant.id
  const filters: FilterDef[] = [
    { type: 'text', name: 'username', placeholder: t('common.username') },
    { type: 'text', name: 'full_name', placeholder: t('rbac.displayName') },
    {
      type: 'select',
      name: 'is_active',
      label: t('table.allStatuses'),
      options: [
        { value: 'true', label: t('rbac.enabled') },
        { value: 'false', label: t('rbac.disabled') },
      ],
    },
    {
      type: 'select',
      name: 'role_id',
      label: t('table.allRoles'),
      optionsKey: ['tenant-roles', tid, 'options'],
      loadOptions: () =>
        tid
          ? api.tenants
              .roles(tid, ALL)
              .then((r) =>
                r.data.map((x) => ({ value: x.id, label: roleLabel(x) }))
              )
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
    roles.data?.data.map((r) => ({
      value: r.name,
      label: roleLabel(r),
    })) ?? []
  const roleName = (n: string) =>
    roleOptions.find((o) => o.value === n)?.label ?? n
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
            header: t('common.username'),
            cell: (r) => (
              <span className='font-medium'>
                {r.username || r.email}
                {r.user_id === me?.id && (
                  <span className='ms-1 text-muted-foreground'>
                    {t('common.you')}
                  </span>
                )}
              </span>
            ),
          },
          {
            header: t('rbac.displayName'),
            sortKey: 'full_name',
            cell: (r) => r.full_name ?? '—',
          },
          {
            header: t('common.email'),
            sortKey: 'email',
            cell: (r) => (
              <span className='text-muted-foreground'>{r.email}</span>
            ),
          },
          {
            header: t('common.roles'),
            cell: (r) => (
              <div className='flex flex-wrap gap-1'>
                {r.roles.map((x) => (
                  <Badge
                    key={x}
                    variant={x === 'owner' ? 'default' : 'secondary'}
                  >
                    {roleName(x)}
                  </Badge>
                ))}
                {!r.roles.length && '—'}
              </div>
            ),
          },
          {
            header: t('common.status'),
            cell: (r) => <StatusBadge active={r.is_active !== false} />,
          },
          {
            header: t('rbac.actions'),
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
        title={s.editing ? t('members.edit') : t('members.add')}
        description={s.editing ? undefined : t('members.addDesc')}
        fields={[
          {
            name: 'email',
            label: t('common.email'),
            type: 'email',
            required: true,
            readOnly: !!s.editing,
          },
          {
            name: 'username',
            label: t('common.username'),
            readOnly: true,
            hidden: !s.editing,
          },
          {
            name: 'full_name',
            label: t('rbac.displayName'),
            readOnly: true,
            hidden: !s.editing,
          },
          {
            name: 'roles',
            label: t('roles.tenantTitle'),
            type: 'tags',
            options: roleOptions,
            placeholder: t('rbac.pickRoles'),
          },
        ]}
        initial={{
          email: s.editing?.email ?? '',
          username: s.editing?.username ?? '',
          full_name: s.editing?.full_name ?? '',
          roles: s.editing?.roles ?? ['member'],
        }}
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
        desc={t('members.removeDesc', {
          email: s.deleting?.email,
          tenant: current?.tenant.name,
        })}
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
