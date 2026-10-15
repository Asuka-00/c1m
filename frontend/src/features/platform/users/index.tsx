/** 平台用户管理页面：筛选、列表、编辑（角色标签多选 + 状态单选）、重置密码、删除。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { KeyRound, Plus } from 'lucide-react'
import { ALL, api, type User, type UserIn } from '@/lib/api'
import { useApiMutation, useCan, useMe } from '@/lib/api/hooks'
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
  type Values,
  type FilterDef,
} from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { StatusBadge } from '../rbac/status'
import { statusOptions } from '../rbac/status-options'
import { TenantRolesEditor } from './tenant-roles-editor'
import { decodeRows, encodeRows } from './tenant-rows'

/** 用户管理（平台）：用户 CRUD、启停、平台角色分配与重置密码。 */
export default function UsersPage() {
  const can = useCan()
  const { data: me } = useMe()
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
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['users', lp.query],
    queryFn: () => api.users.list(lp.query),
  })
  const roles = useQuery({
    queryKey: ['roles', 'all'],
    queryFn: () => api.roles.list(ALL),
  })
  const roleOptions =
    roles.data?.data.map((r) => ({ value: r.id, label: roleLabel(r) })) ?? []
  const s = useCrudState<User>()
  const editing = s.editing
  const userRoles = useQuery({
    queryKey: ['user-roles', editing?.id],
    queryFn: () => api.users.roles(editing!.id),
    enabled: !!editing,
  })
  const userTenants = useQuery({
    queryKey: ['user-tenants', editing?.id],
    queryFn: () => api.users.tenants(editing!.id),
    enabled: !!editing,
  })
  const [resetFor, setResetFor] = useState<User | null>(null)
  const save = useApiMutation(
    async (v: Values) => {
      const b: UserIn = {
        full_name: (v.full_name as string) || null,
        is_active: v.status === 'active',
      }
      b.email = ((v.email as string) || '').trim() || null
      const roleIds = v.roles as string[]
      const rows = decodeRows(v.tenants as string[])
      if (editing) {
        await api.users.update(editing.id, b)
        await api.users.setTenants(editing.id, rows)
        return api.users.setRoles(editing.id, roleIds)
      }
      const u = await api.users.create({
        ...b,
        username: (v.username as string).trim(),
        password: v.password as string,
      })
      // 不会自动创建租户：按所选行分配
      if (rows.length) await api.users.setTenants(u.id, rows)
      return roleIds.length ? api.users.setRoles(u.id, roleIds) : u
    },
    [['users'], ['user-roles'], ['user-tenants'], ['platform-tenants']],
    t('rbac.saved')
  )
  const reset = useApiMutation(
    (v: { id: string; password: string }) =>
      api.users.update(v.id, { password: v.password }),
    [['users']],
    t('rbac.passwordReset')
  )
  const remove = useApiMutation(
    api.users.remove,
    [['users']],
    t('users.deleted')
  )
  const writable = can('users:write')
  return (
    <Page
      title={t('users.title')}
      description={t('users.desc')}
      actions={
        writable && (
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
            header: t('common.username'),
            sortKey: 'username',
            cell: (r) => <span className='font-medium'>{r.username}</span>,
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
              <span className='text-muted-foreground'>{r.email ?? '—'}</span>
            ),
          },
          {
            header: t('common.roles'),
            cell: (r) => (
              <div className='flex flex-wrap gap-1'>
                {r.is_superuser && <Badge>{t('common.superuser')}</Badge>}
                {r.role_names?.map((x) => (
                  <Badge key={x} variant='secondary'>
                    {roleLabel(
                      roles.data?.data.find((o) => o.name === x) ?? { name: x }
                    )}
                  </Badge>
                ))}
              </div>
            ),
          },
          {
            header: t('common.status'),
            sortKey: 'is_active',
            cell: (r) => <StatusBadge active={r.is_active} />,
          },
          {
            header: t('rbac.updatedBy'),
            cell: (r) => r.updated_by ?? '—',
          },
          {
            header: t('rbac.updatedAt'),
            sortKey: 'updated_at',
            cell: (r) => fmtDateTime(r.updated_at ?? r.created_at),
          },
          {
            header: t('rbac.actions'),
            className: 'w-32',
            cell: (r) => (
              <RowActions
                onEdit={writable ? () => s.openEdit(r) : undefined}
                onDelete={
                  can('users:delete') && r.id !== me?.id
                    ? () => s.openDelete(r)
                    : undefined
                }
              >
                {writable && (
                  <IconButton
                    label={t('rbac.resetPassword')}
                    variant='ghost'
                    onClick={() => setResetFor(r)}
                  >
                    <KeyRound className='size-4' />
                  </IconButton>
                )}
              </RowActions>
            ),
          },
        ]}
      />
      <FormDialog
        key={`${editing?.id ?? 'new'}-${userRoles.isSuccess}-${userTenants.isSuccess}`}
        open={
          s.formOpen &&
          (!editing || (!userRoles.isLoading && !userTenants.isLoading))
        }
        onOpenChange={(o) => !o && s.closeForm()}
        title={editing ? t('users.edit') : t('users.new')}
        description={editing ? undefined : t('users.newDesc')}
        fields={[
          {
            name: 'username',
            label: t('common.username'),
            required: true,
            readOnly: !!editing,
            placeholder: t('users.usernameHint'),
          },
          {
            name: 'email',
            label: t('common.email'),
            type: 'email',
            placeholder: t('users.emailOptional'),
          },
          { name: 'full_name', label: t('rbac.displayName') },
          {
            name: 'password',
            label: t('common.password'),
            type: 'password',
            required: true,
            hidden: !!editing,
            placeholder: t('users.passwordMin'),
          },
          {
            name: 'roles',
            label: t('common.roles'),
            type: 'tags',
            options: roleOptions,
            placeholder: t('rbac.pickRoles'),
          },
          {
            name: 'status',
            label: t('common.status'),
            type: 'radio',
            options: statusOptions(),
          },
          {
            name: 'tenants',
            label: t('users.tenants'),
            type: 'custom',
            render: (val, onChange) => (
              <TenantRolesEditor
                value={val as string[]}
                onChange={(x) => onChange(x)}
              />
            ),
          },
        ]}
        initial={{
          username: editing?.username ?? '',
          email: editing?.email ?? '',
          full_name: editing?.full_name ?? '',
          password: '',
          roles: userRoles.data?.map((r) => r.id) ?? [],
          status: editing && !editing.is_active ? 'disabled' : 'active',
          tenants: encodeRows(userTenants.data ?? []),
        }}
        pending={save.isPending}
        onSubmit={(v) => save.mutateAsync(v)}
      />
      <FormDialog
        open={!!resetFor}
        onOpenChange={(o) => !o && setResetFor(null)}
        title={t('rbac.resetPassword')}
        description={t('rbac.resetPasswordDesc', {
          name: resetFor?.username,
        })}
        fields={[
          {
            name: 'password',
            label: t('rbac.newPassword'),
            type: 'password',
            required: true,
            placeholder: t('users.passwordMin'),
          },
        ]}
        initial={{ password: '' }}
        pending={reset.isPending}
        onSubmit={(v) =>
          reset.mutateAsync({
            id: resetFor!.id,
            password: v.password as string,
          })
        }
      />
      <ConfirmDialog
        open={!!s.deleting}
        onOpenChange={(o) => !o && s.closeDelete()}
        title={t('users.delete')}
        desc={t('users.deleteDesc', { email: s.deleting?.username })}
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
