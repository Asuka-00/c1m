/** 权限管理页面。 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Plus, Save } from 'lucide-react'
import { ALL, api, type Permission, type Role } from '@/lib/api'
import { useApiMutation, useCan, useCurrentTenant } from '@/lib/api/hooks'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
import { PermissionTree } from './permission-tree'

type Scope = 'platform' | 'tenant'

/** 权限管理：按资源分组的权限列表与 CRUD。 */
export default function PermissionsPage() {
  const can = useCan()
  const current = useCurrentTenant()
  const [scope, setScope] = useState<Scope>('platform')
  const [roleId, setRoleId] = useState<string | null>(null)
  const perms = useQuery({
    queryKey: ['permissions', 'all'],
    queryFn: () => api.permissions.list(ALL),
  })
  const filters: FilterDef[] = [
    searchFilter(t('table.searchPermissions')),
    {
      type: 'select',
      name: 'scope',
      label: t('table.allScopes'),
      options: [
        { value: 'platform', label: t('permissions.scopes.platform') },
        { value: 'tenant', label: t('permissions.scopes.tenant') },
      ],
    },
  ]
  const lp = useListParams(filters)
  const permsPage = useQuery({
    queryKey: ['permissions', lp.query],
    queryFn: () => api.permissions.list(lp.query),
  })
  const platformRoles = useQuery({
    queryKey: ['roles', 'all'],
    queryFn: () => api.roles.list(ALL),
  })
  const tid = current?.tenant.id
  const tenantRoles = useQuery({
    queryKey: ['tenant-roles', tid, 'all'],
    queryFn: () => api.tenants.roles(tid!, ALL),
    enabled: !!tid,
  })
  const roles: Role[] =
    (scope === 'platform'
      ? platformRoles.data?.data
      : tenantRoles.data?.data) ?? []
  const role = roles.find((r) => r.id === roleId) ?? roles[0]
  // 租户角色只能包含租户作用域的权限
  const visiblePerms = useMemo(
    () =>
      (perms.data?.data ?? []).filter(
        (p) => scope === 'platform' || p.scope === 'tenant'
      ),
    [perms.data, scope]
  )

  const editable =
    !!role &&
    (scope === 'platform'
      ? can('roles:write')
      : can('tenant:manage') && role.name !== 'owner')
  // 权限 CRUD
  const s = useCrudState<Permission>()
  const create = useApiMutation(
    api.permissions.create,
    [['permissions']],
    t('permissions.created')
  )
  const update = useApiMutation(
    (v: { id: string; description: string; scope: string }) =>
      api.permissions.update(v.id, v),
    [['permissions']],
    t('permissions.updated')
  )
  const remove = useApiMutation(
    api.permissions.remove,
    [['permissions'], ['roles']],
    t('permissions.deleted')
  )

  return (
    <Page title={t('common.permissions')} description={t('permissions.desc')}>
      <Tabs
        value={scope}
        onValueChange={(v) => {
          setScope(v as Scope)
          setRoleId(null)
        }}
      >
        <TabsList>
          <TabsTrigger value={'platform'}>
            {t('permissions.platformTab')}
          </TabsTrigger>
          <TabsTrigger value={'tenant'} disabled={!tid}>
            {t('permissions.tenantTab')}{' '}
            {current ? `(${current.tenant.name})` : ''}
          </TabsTrigger>
        </TabsList>
      </Tabs>
      <div className='grid gap-4 lg:grid-cols-[240px_1fr]'>
        <Card className='py-2'>
          <CardContent className='grid gap-1 px-2'>
            {roles.map((r) => (
              <button
                key={r.id}
                type='button'
                onClick={() => setRoleId(r.id)}
                className={cn(
                  'rounded-md px-3 py-2 text-start text-sm hover:bg-muted',
                  role?.id === r.id && 'bg-muted font-medium'
                )}
              >
                {r.name}
                <span className='block text-xs text-muted-foreground'>
                  {t('permissions.count', { count: r.permissions.length })}
                </span>
              </button>
            ))}
          </CardContent>
        </Card>
        {role ? (
          <RoleEditor
            key={`${scope}-${role.id}-${role.permissions.length}`}
            role={role}
            scope={scope}
            tid={tid}
            perms={visiblePerms}
            editable={editable}
          />
        ) : (
          <Card>
            <CardContent className='text-muted-foreground'>
              {t('permissions.noRoles')}
            </CardContent>
          </Card>
        )}
      </div>

      <div className='mt-4 flex items-center justify-between'>
        <h3 className='text-lg font-semibold'>{t('permissions.all')}</h3>
        {can('roles:write') && (
          <Button variant='outline' onClick={s.openCreate}>
            <Plus /> {t('permissions.new')}
          </Button>
        )}
      </div>
      <DataTable
        rows={permsPage.data?.data}
        total={permsPage.data?.count}
        params={lp}
        filters={filters}
        loading={permsPage.isLoading}
        rowKey={(r) => r.id}
        columns={[
          {
            header: t('permissions.code'),
            sortKey: 'code',
            cell: (r) => <span className='font-mono text-xs'>{r.code}</span>,
          },
          {
            header: t('permissions.scope'),
            sortKey: 'scope',
            cell: (r) =>
              t(`permissions.scopes.${r.scope}`, { defaultValue: r.scope }),
          },
          {
            header: t('common.description'),
            sortKey: 'description',
            cell: (r) => r.description ?? '',
          },
          {
            header: '',
            className: 'w-24',
            cell: (r) =>
              can('roles:write') && (
                <RowActions
                  onEdit={() => s.openEdit(r)}
                  onDelete={() => s.openDelete(r)}
                />
              ),
          },
        ]}
      />
      <FormDialog
        open={s.formOpen}
        onOpenChange={(o) => !o && s.closeForm()}
        title={s.editing ? t('permissions.edit') : t('permissions.new')}
        fields={[
          {
            name: 'code',
            label: t('permissions.codeLabel'),
            required: true,
            hidden: !!s.editing,
          },
          {
            name: 'scope',
            label: t('permissions.scope'),
            type: 'select',
            options: [
              { value: 'platform', label: t('permissions.scopes.platform') },
              { value: 'tenant', label: t('permissions.scopes.tenant') },
            ],
          },
          { name: 'description', label: t('common.description') },
        ]}
        initial={{
          code: s.editing?.code ?? '',
          scope: s.editing?.scope ?? 'platform',
          description: s.editing?.description ?? '',
        }}
        onSubmit={(v) =>
          s.editing
            ? update.mutateAsync({
                id: s.editing.id,
                description: v.description as string,
                scope: v.scope as string,
              })
            : create.mutateAsync({
                code: v.code as string,
                scope: v.scope as string,
                description: v.description as string,
              })
        }
      />
      <ConfirmDialog
        open={!!s.deleting}
        onOpenChange={(o) => !o && s.closeDelete()}
        title={t('permissions.delete')}
        desc={t('permissions.deleteDesc', { code: s.deleting?.code })}
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

function RoleEditor({
  role,
  scope,
  tid,
  perms,
  editable,
}: {
  role: Role
  scope: Scope
  tid?: string
  perms: Permission[]
  editable: boolean
}) {
  const [sel, setSel] = useState<Set<string>>(
    () => new Set(role.permissions.map((p) => p.code))
  )
  const save = useApiMutation(
    () =>
      scope === 'platform'
        ? api.roles.setPermissions(role.id, [...sel])
        : api.tenants.setRolePermissions(tid!, role.id, [...sel]),
    [['roles'], ['tenant-roles'], ['menus']],
    t('permissions.saved')
  )
  const dirty =
    [...sel].sort().join() !==
    role.permissions
      .map((p) => p.code)
      .sort()
      .join()
  return (
    <Card>
      <CardHeader className='flex flex-row items-start justify-between'>
        <div>
          <CardTitle>{t('permissions.role', { name: role.name })}</CardTitle>
          <CardDescription>
            {scope === 'tenant' ? t('permissions.tenantOnly') + ' ' : ''}
            {role.name === 'owner' && scope === 'tenant'
              ? t('permissions.ownerFixed')
              : ''}
            {t('permissions.selected', { count: sel.size })}
          </CardDescription>
        </div>
        {editable && (
          <Button
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate(undefined)}
          >
            <Save /> {t('common.save')}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <PermissionTree
          perms={perms}
          value={sel}
          onChange={setSel}
          disabled={!editable}
        />
      </CardContent>
    </Card>
  )
}
