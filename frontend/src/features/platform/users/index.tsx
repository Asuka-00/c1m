/** 用户管理页面。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Plus, ShieldPlus } from 'lucide-react'
import { ALL, api, type User, type UserIn } from '@/lib/api'
import { useApiMutation, useCan, useMe } from '@/lib/api/hooks'
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
  type Values,
  type FilterDef,
  searchFilter,
  boolOptions,
} from '@/components/crud'

function UserRolesDialog({
  user,
  onClose,
}: {
  user: User | null
  onClose: () => void
}) {
  const roles = useQuery({
    queryKey: ['roles', 'all'],
    queryFn: () => api.roles.list(ALL),
  })
  const userRoles = useQuery({
    queryKey: ['user-roles', user?.id],
    queryFn: () => api.users.roles(user!.id),
    enabled: !!user,
  })
  const add = useApiMutation(
    (rid: string) => api.users.addRole(user!.id, rid),
    [['user-roles']]
  )
  const del = useApiMutation(
    (rid: string) => api.users.removeRole(user!.id, rid),
    [['user-roles']]
  )
  const has = new Set(userRoles.data?.map((r) => r.id))
  return (
    <FormDialog
      open={!!user}
      onOpenChange={(o) => !o && onClose()}
      title={t('users.rolesTitle', { email: user?.email ?? '' })}
      description={t('users.rolesDesc')}
      fields={[
        {
          name: 'roles',
          label: t('common.roles'),
          type: 'multi',
          options:
            roles.data?.data.map((r) => ({ value: r.id, label: r.name })) ?? [],
        },
      ]}
      initial={{ roles: [...has] as string[] }}
      onSubmit={async (v) => {
        const want = new Set(v.roles as string[])
        for (const r of roles.data?.data ?? []) {
          if (want.has(r.id) && !has.has(r.id)) await add.mutateAsync(r.id)
          if (!want.has(r.id) && has.has(r.id)) await del.mutateAsync(r.id)
        }
      }}
    />
  )
}

/** 用户管理（平台）：用户 CRUD、启停与平台角色分配。 */
export default function UsersPage() {
  const can = useCan()
  const { data: me } = useMe()
  const filters: FilterDef[] = [
    searchFilter(t('table.searchUsers')),
    {
      type: 'select',
      name: 'role_id',
      label: t('table.allRoles'),
      optionsKey: ['roles', 'all', 'options'],
      loadOptions: () =>
        api.roles
          .list(ALL)
          .then((r) => r.data.map((x) => ({ value: x.id, label: x.name }))),
    },
    {
      type: 'select',
      name: 'is_active',
      label: t('table.allStatuses'),
      options: boolOptions(t('common.activeBadge'), t('common.inactive')),
    },
    {
      type: 'select',
      name: 'is_superuser',
      label: t('table.allSuperuser'),
      options: boolOptions(t('common.superuser'), t('users.regular')),
    },
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['users', lp.query],
    queryFn: () => api.users.list(lp.query),
  })
  const s = useCrudState<User>()
  const [rolesFor, setRolesFor] = useState<User | null>(null)
  const create = useApiMutation(
    api.users.create,
    [['users']],
    t('users.created')
  )
  const update = useApiMutation(
    (v: { id: string } & UserIn) => api.users.update(v.id, v),
    [['users']],
    t('users.updated')
  )
  const remove = useApiMutation(
    api.users.remove,
    [['users']],
    t('users.deleted')
  )
  const toBody = (v: Values): UserIn => {
    const b: UserIn = {
      email: v.email as string,
      username: ((v.username as string) || '').trim() || null,
      full_name: (v.full_name as string) || null,
      is_active: !!v.is_active,
      is_superuser: !!v.is_superuser,
    }
    if (v.password) b.password = v.password as string
    return b
  }
  return (
    <Page
      title={t('users.title')}
      description={t('users.desc')}
      actions={
        can('users:write') && (
          <Button onClick={s.openCreate}>
            <Plus /> {t('users.new')}
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
            header: t('common.email'),
            sortKey: 'email',
            cell: (r) => <span className='font-medium'>{r.email}</span>,
          },
          {
            header: t('common.username'),
            sortKey: 'username',
            cell: (r) =>
              r.username ? (
                <code className='text-xs'>{r.username}</code>
              ) : (
                <span className='text-muted-foreground'>—</span>
              ),
          },
          {
            header: t('common.name'),
            sortKey: 'full_name',
            cell: (r) => r.full_name ?? '—',
          },
          {
            header: t('common.status'),
            sortKey: 'is_active',
            cell: (r) => (
              <Badge variant={r.is_active ? 'secondary' : 'outline'}>
                {r.is_active ? t('common.activeBadge') : t('common.inactive')}
              </Badge>
            ),
          },
          {
            header: t('common.superuser'),
            sortKey: 'is_superuser',
            cell: (r) =>
              r.is_superuser ? <Badge>{t('common.superuser')}</Badge> : '',
          },
          {
            header: '',
            className: 'w-32',
            cell: (r) => (
              <RowActions
                onEdit={can('users:write') ? () => s.openEdit(r) : undefined}
                onDelete={
                  can('users:delete') && r.id !== me?.id
                    ? () => s.openDelete(r)
                    : undefined
                }
              >
                {can('roles:write') && (
                  <Button
                    size='icon'
                    variant='ghost'
                    aria-label={t('common.roles')}
                    onClick={() => setRolesFor(r)}
                  >
                    <ShieldPlus className='size-4' />
                  </Button>
                )}
              </RowActions>
            ),
          },
        ]}
      />
      <FormDialog
        open={s.formOpen}
        onOpenChange={(o) => !o && s.closeForm()}
        title={s.editing ? t('users.edit') : t('users.new')}
        description={s.editing ? t('users.editDesc') : t('users.newDesc')}
        fields={[
          {
            name: 'email',
            label: t('common.email'),
            type: 'email',
            required: true,
          },
          {
            name: 'username',
            label: t('common.username'),
            placeholder: t('users.usernameHint'),
          },
          { name: 'full_name', label: t('common.fullName') },
          {
            name: 'password',
            label: t('common.password'),
            type: 'password',
            required: !s.editing,
            placeholder: s.editing
              ? t('users.passwordUnchanged')
              : t('users.passwordMin'),
          },
          { name: 'is_active', label: t('common.active'), type: 'checkbox' },
          {
            name: 'is_superuser',
            label: t('common.superuser'),
            type: 'checkbox',
          },
        ]}
        initial={{
          email: s.editing?.email ?? '',
          username: s.editing?.username ?? '',
          full_name: s.editing?.full_name ?? '',
          password: '',
          is_active: s.editing?.is_active ?? true,
          is_superuser: s.editing?.is_superuser ?? false,
        }}
        pending={create.isPending || update.isPending}
        onSubmit={(v) =>
          s.editing
            ? update.mutateAsync({ id: s.editing.id, ...toBody(v) })
            : create.mutateAsync(toBody(v))
        }
      />
      <ConfirmDialog
        open={!!s.deleting}
        onOpenChange={(o) => !o && s.closeDelete()}
        title={t('users.delete')}
        desc={t('users.deleteDesc', { email: s.deleting?.email })}
        destructive
        confirmText={t('common.delete')}
        handleConfirm={() =>
          s.deleting &&
          remove.mutate(s.deleting.id, { onSuccess: s.closeDelete })
        }
      />
      <UserRolesDialog user={rolesFor} onClose={() => setRolesFor(null)} />
    </Page>
  )
}
