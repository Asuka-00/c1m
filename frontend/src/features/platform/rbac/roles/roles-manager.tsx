/** 角色管理组件（平台 / 租户共用）：列表 + 含嵌入权限树的新增 / 编辑对话框。 */
import { useQuery } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { Plus } from 'lucide-react'
import { api, type Role } from '@/lib/api'
import { useApiMutation, useCan, useCurrentTenant } from '@/lib/api/hooks'
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
import { PermissionTreeSelect } from '../permission-tree-select'
import { StatusBadge } from '../status'
import { statusFilter, statusOptions } from '../status-options'

/** 平台角色（/platform/roles）或租户角色（/tenants/{id}/roles）的 CRUD；
 *  权限在对话框内的三态权限树中勾选（租户仅显示租户作用域权限）。 */
export function RolesManager({ scope }: { scope: 'platform' | 'tenant' }) {
  const can = useCan()
  const current = useCurrentTenant()
  const tid = current?.tenant.id
  const platform = scope === 'platform'
  const filters: FilterDef[] = [
    { type: 'text', name: 'code', placeholder: t('rbac.roleCode') },
    { type: 'text', name: 'title', placeholder: t('rbac.roleName') },
    statusFilter(),
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: platform ? ['roles', lp.query] : ['tenant-roles', tid, lp.query],
    queryFn: () =>
      platform ? api.roles.list(lp.query) : api.tenants.roles(tid!, lp.query),
    enabled: platform || !!tid,
  })
  const s = useCrudState<Role>()
  const tree = useQuery({
    queryKey: ['permission-tree', 'role', platform, tid],
    queryFn: () =>
      platform ? api.permissions.tree() : api.tenants.permissionTree(tid!),
    enabled: s.formOpen && (platform || !!tid),
  })
  const builtin = (r: Role) =>
    (platform ? ['admin', 'user'] : ['owner']).includes(r.name)
  const locked = (r: Role) => !platform && r.name === 'owner'
  const writable = platform ? can('roles:write') : can('tenant:manage')
  const keys = [['roles'], ['tenant-roles'], ['menus']]
  const save = useApiMutation(
    async (v: Values) => {
      const codes = v.codes as string[]
      const b = {
        name: v.name as string,
        title: (v.title as string) || null,
        description: (v.description as string) || null,
        status: v.status as string,
      }
      const e = s.editing
      if (!e)
        return platform
          ? api.roles.create({ ...b, permission_codes: codes })
          : api.tenants.createRole(tid!, { ...b, permission_codes: codes })
      if (platform) {
        await api.roles.update(e.id, b)
        return api.roles.setPermissions(e.id, codes)
      }
      await api.tenants.updateRole(tid!, e.id, b)
      return locked(e) ? e : api.tenants.setRolePermissions(tid!, e.id, codes)
    },
    keys,
    t('rbac.saved')
  )
  const remove = useApiMutation(
    (id: string) =>
      platform ? api.roles.remove(id) : api.tenants.removeRole(tid!, id),
    keys,
    t('roles.deleted')
  )
  const e = s.editing
  return (
    <Page
      title={platform ? t('common.roles') : t('roles.tenantTitle')}
      description={
        platform
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
            header: t('rbac.roleCode'),
            sortKey: 'name',
            cell: (r) => <code className='text-xs'>{r.name}</code>,
          },
          {
            header: t('rbac.roleName'),
            sortKey: 'title',
            cell: (r) => (
              <span className='font-medium'>{r.title || r.name}</span>
            ),
          },
          {
            header: t('common.description'),
            cell: (r) => (
              <span className='text-muted-foreground'>
                {r.description ?? ''}
              </span>
            ),
          },
          {
            header: t('rbac.permCount'),
            cell: (r) => r.permissions.length,
          },
          {
            header: t('common.status'),
            sortKey: 'status',
            cell: (r) => <StatusBadge active={r.status !== 'disabled'} />,
          },
          {
            header: t('rbac.updatedBy'),
            cell: (r) => r.updated_by ?? '—',
          },
          {
            header: t('rbac.updatedAt'),
            sortKey: 'updated_at',
            cell: (r) => fmtDateTime(r.updated_at),
          },
          {
            header: t('rbac.actions'),
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
        title={e ? t('roles.edit') : t('roles.new')}
        description={e && locked(e) ? t('permissions.ownerFixed') : undefined}
        fields={[
          {
            name: 'name',
            label: t('rbac.roleCode'),
            required: true,
            readOnly: !!e && builtin(e),
          },
          { name: 'title', label: t('rbac.roleName'), required: true },
          { name: 'description', label: t('common.description') },
          {
            name: 'status',
            label: t('common.status'),
            type: 'radio',
            options: statusOptions(),
            hidden: !!e && locked(e),
          },
          {
            name: 'codes',
            label: t('rbac.permTree'),
            type: 'custom',
            render: (v, set) =>
              tree.isLoading ? (
                <p className='text-sm text-muted-foreground'>
                  {t('common.loading')}
                </p>
              ) : (
                <PermissionTreeSelect
                  nodes={tree.data ?? []}
                  value={v as string[]}
                  onChange={set}
                  disabled={!!e && locked(e)}
                />
              ),
          },
        ]}
        initial={{
          name: e?.name ?? '',
          title: e?.title || e?.name || '',
          description: e?.description ?? '',
          status: e?.status ?? 'active',
          codes: e?.permissions.map((p) => p.code) ?? [],
        }}
        pending={save.isPending}
        onSubmit={(v) => save.mutateAsync(v)}
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
