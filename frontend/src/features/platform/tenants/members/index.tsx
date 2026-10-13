/** 租户成员页面。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { KeyRound, UserPlus, UserRoundPlus } from 'lucide-react'
import { ALL, api, type Member, type MemberUserIn } from '@/lib/api'
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
  type Values,
} from '@/components/crud'
import { StatusBadge } from '../../rbac/status'
import { statusOptions } from '../../rbac/status-options'

/** 租户成员（用户与权限 · 用户）：按用户名 / 显示名 / 状态 / 角色筛选，
 *  标签多选分配租户角色；新建用户、按用户名添加已有用户、移除成员；
 *  仅当成员只属于本租户时可修改其账号与重置密码（否则需平台管理员）。 */
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
  const [creating, setCreating] = useState(false)
  const [resetFor, setResetFor] = useState<Member | null>(null)
  const create = useApiMutation(
    (v: Values) =>
      api.tenants.createUser(tid!, {
        username: (v.username as string).trim(),
        full_name: (v.full_name as string) || null,
        email: ((v.email as string) || '').trim() || null,
        password: v.password as string,
        roles: v.roles as string[],
        is_active: v.status === 'active',
      }),
    keys,
    t('members.created')
  )
  const updateUser = useApiMutation(
    (b: { user_id: string } & MemberUserIn) => {
      const { user_id, ...rest } = b
      return api.tenants.updateUser(tid!, user_id, rest)
    },
    keys,
    t('rbac.saved')
  )
  const add = useApiMutation(
    (b: { username: string; roles: string[] }) =>
      api.tenants.addMember(tid!, b),
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
  /** 仅只属于本租户的成员（且非本人）可在此修改账号信息 */
  const editableUser =
    !!s.editing && !!s.editing.sole_tenant && s.editing.user_id !== me?.id
  return (
    <Page
      title={t('menu.members')}
      description={t('members.desc', { tenant: current?.tenant.name ?? '…' })}
      actions={
        writable && (
          <div className='flex gap-2'>
            <Button variant='outline' onClick={s.openCreate}>
              <UserPlus /> {t('members.addExisting')}
            </Button>
            <Button onClick={() => setCreating(true)}>
              <UserRoundPlus /> {t('members.createUser')}
            </Button>
          </div>
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
            sortKey: 'username',
            cell: (r) => (
              <span className='font-medium'>
                {r.username}
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
              <span className='text-muted-foreground'>{r.email ?? '—'}</span>
            ),
          },
          {
            header: t('common.roles'),
            cell: (r) => (
              <div className='flex flex-wrap gap-1'>
                {r.roles.map((x) => (
                  <Badge key={x} variant='secondary'>
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
            className: 'w-32',
            cell: (r) => (
              <RowActions
                onEdit={writable ? () => s.openEdit(r) : undefined}
                onDelete={
                  writable || r.user_id === me?.id
                    ? () => s.openDelete(r)
                    : undefined
                }
              >
                {writable && r.sole_tenant && r.user_id !== me?.id && (
                  <Button
                    size='icon'
                    variant='ghost'
                    aria-label={t('rbac.resetPassword')}
                    title={t('rbac.resetPassword')}
                    onClick={() => setResetFor(r)}
                  >
                    <KeyRound className='size-4' />
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
        title={s.editing ? t('members.edit') : t('members.addExisting')}
        description={
          s.editing
            ? s.editing.sole_tenant
              ? undefined
              : t('members.sharedUser')
            : t('members.addDesc')
        }
        fields={[
          {
            name: 'username',
            label: t('common.username'),
            required: true,
            readOnly: !!s.editing,
            placeholder: t('members.usernameHint'),
          },
          {
            name: 'full_name',
            label: t('rbac.displayName'),
            readOnly: !editableUser,
            hidden: !s.editing,
          },
          {
            name: 'email',
            label: t('common.email'),
            type: 'email',
            readOnly: !editableUser,
            hidden: !s.editing,
            placeholder: t('users.emailOptional'),
          },
          {
            name: 'roles',
            label: t('roles.tenantTitle'),
            type: 'tags',
            options: roleOptions,
            placeholder: t('rbac.pickRoles'),
          },
          {
            name: 'status',
            label: t('common.status'),
            type: 'radio',
            options: statusOptions(),
            hidden: !editableUser,
          },
        ]}
        initial={{
          email: s.editing?.email ?? '',
          username: s.editing?.username ?? '',
          full_name: s.editing?.full_name ?? '',
          roles: s.editing?.roles ?? ['member'],
          status: s.editing?.is_active === false ? 'disabled' : 'active',
        }}
        onSubmit={async (v) => {
          if (!s.editing)
            return add.mutateAsync({
              username: (v.username as string).trim(),
              roles: v.roles as string[],
            })
          if (editableUser)
            await updateUser.mutateAsync({
              user_id: s.editing.user_id,
              full_name: (v.full_name as string) || null,
              email: ((v.email as string) || '').trim() || null,
              is_active: v.status === 'active',
            })
          return setRoles.mutateAsync({
            user_id: s.editing.user_id,
            roles: v.roles as string[],
          })
        }}
      />
      <FormDialog
        open={creating}
        onOpenChange={setCreating}
        title={t('members.createUser')}
        description={t('members.createDesc')}
        fields={[
          {
            name: 'username',
            label: t('common.username'),
            required: true,
            placeholder: t('users.usernameHint'),
          },
          { name: 'full_name', label: t('rbac.displayName') },
          {
            name: 'email',
            label: t('common.email'),
            type: 'email',
            placeholder: t('users.emailOptional'),
          },
          {
            name: 'password',
            label: t('members.initialPassword'),
            type: 'password',
            required: true,
            placeholder: t('users.passwordMin'),
          },
          {
            name: 'roles',
            label: t('roles.tenantTitle'),
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
        ]}
        initial={{
          username: '',
          full_name: '',
          email: '',
          password: '',
          roles: ['member'],
          status: 'active',
        }}
        pending={create.isPending}
        onSubmit={(v) => create.mutateAsync(v)}
      />
      <FormDialog
        open={!!resetFor}
        onOpenChange={(o) => !o && setResetFor(null)}
        title={t('rbac.resetPassword')}
        description={t('rbac.resetPasswordDesc', { name: resetFor?.username })}
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
        pending={updateUser.isPending}
        onSubmit={(v) =>
          updateUser.mutateAsync({
            user_id: resetFor!.user_id,
            password: v.password as string,
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
          email: s.deleting?.username,
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
