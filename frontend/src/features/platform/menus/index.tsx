/** 菜单管理页面。 */
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Plus } from 'lucide-react'
import { ALL, api, type Menu } from '@/lib/api'
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
  type Values,
  type FilterDef,
  searchFilter,
  boolOptions,
} from '@/components/crud'
import { ICONS } from '@/components/layout/icons'
import { COMPONENTS } from '@/features/shell/dynamic/registry'

/** 菜单管理：树形列表，编辑标题 / 图标 / 排序 / 隐藏，新增自定义菜单。 */
export default function MenusPage() {
  const filters: FilterDef[] = [
    searchFilter(t('table.searchMenus')),
    {
      type: 'select',
      name: 'parent_id',
      label: t('table.allParents'),
      optionsKey: ['menus', 'all', 'groups'],
      loadOptions: () =>
        api.menus.list(ALL).then((r) =>
          r.data
            .filter((m) => !m.path)
            .map((m) => ({
              value: m.id,
              label: t(`menu.${m.key}`, { defaultValue: m.title }),
            }))
        ),
    },
    {
      type: 'select',
      name: 'hidden',
      label: t('table.allVisibility'),
      options: boolOptions(t('menus.hidden'), t('table.visible')),
    },
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['menus', 'page', lp.query],
    queryFn: () => api.menus.list(lp.query),
  })
  const all = useQuery({
    queryKey: ['menus', 'all'],
    queryFn: () => api.menus.list(ALL),
  })
  const perms = useQuery({
    queryKey: ['permissions', 'all'],
    queryFn: () => api.permissions.list(ALL),
  })
  const s = useCrudState<Menu>()
  const keys = [['menus']]
  const create = useApiMutation(api.menus.create, keys, t('menus.created'))
  const update = useApiMutation(
    (b: Partial<Menu> & { id: string }) => api.menus.update(b.id, b),
    keys,
    t('menus.updated')
  )
  const remove = useApiMutation(api.menus.remove, keys, t('menus.deleted'))
  const byId = new Map(all.data?.data.map((m) => [m.id, m]))
  const NONE = '__none__'
  const toBody = (v: Values): Partial<Menu> => ({
    title: v.title as string,
    path: (v.path as string) || null,
    icon: v.icon === NONE ? null : (v.icon as string) || null,
    component: v.component === NONE ? null : (v.component as string) || null,
    permission: v.permission === NONE ? null : (v.permission as string) || null,
    parent_id: v.parent_id === NONE ? null : (v.parent_id as string) || null,
    sort_order: Number(v.sort_order) || 0,
    hidden: !!v.hidden,
  })
  const opt = (xs: string[]) => [
    { value: NONE, label: t('common.none') },
    ...xs.map((x) => ({ value: x, label: x })),
  ]
  return (
    <Page
      title={t('menus.title')}
      description={t('menus.desc')}
      actions={
        <Button onClick={s.openCreate}>
          <Plus /> {t('menus.new')}
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
            header: t('common.title'),
            sortKey: 'title',
            cell: (r) => (
              <span className={r.parent_id ? 'ps-6' : 'font-semibold'}>
                {r.title}
              </span>
            ),
          },
          {
            header: t('menus.parent'),
            cell: (r) => byId.get(r.parent_id ?? '')?.title ?? '—',
          },
          {
            header: t('menus.key'),
            sortKey: 'key',
            cell: (r) => <span className='font-mono text-xs'>{r.key}</span>,
          },
          {
            header: t('menus.path'),
            sortKey: 'path',
            cell: (r) => (
              <span className='font-mono text-xs'>
                {r.path ?? t('menus.group')}
              </span>
            ),
          },
          {
            header: t('menus.component'),
            sortKey: 'component',
            cell: (r) => r.component ?? '',
          },
          {
            header: t('menus.permission'),
            sortKey: 'permission',
            cell: (r) =>
              r.permission ? (
                <Badge variant='outline' className='font-mono text-[10px]'>
                  {r.permission}
                </Badge>
              ) : (
                ''
              ),
          },
          {
            header: t('menus.order'),
            sortKey: 'sort_order',
            cell: (r) => r.sort_order,
          },
          {
            header: t('menus.hidden'),
            cell: (r) => (r.hidden ? t('common.yes') : ''),
          },
          {
            header: '',
            className: 'w-24',
            cell: (r) => (
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
        title={s.editing ? t('menus.edit') : t('menus.new')}
        fields={[
          {
            name: 'key',
            label: t('menus.key'),
            required: true,
            hidden: !!s.editing,
          },
          { name: 'title', label: t('common.title'), required: true },
          {
            name: 'parent_id',
            label: t('menus.parentGroup'),
            type: 'select',
            options: [
              { value: NONE, label: t('menus.topLevel') },
              ...(all.data?.data ?? [])
                .filter((m) => !m.path)
                .map((m) => ({ value: m.id, label: m.title })),
            ],
          },
          {
            name: 'path',
            label: t('menus.pathLabel'),
            placeholder: '/reports',
          },
          {
            name: 'component',
            label: t('menus.componentKey'),
            type: 'select',
            options: opt(Object.keys(COMPONENTS)),
          },
          {
            name: 'icon',
            label: t('menus.icon'),
            type: 'select',
            options: opt(Object.keys(ICONS)),
          },
          {
            name: 'permission',
            label: t('menus.requiredPermission'),
            type: 'select',
            options: opt(perms.data?.data.map((p) => p.code) ?? []),
          },
          { name: 'sort_order', label: t('menus.order'), type: 'number' },
          { name: 'hidden', label: t('menus.hidden'), type: 'checkbox' },
        ]}
        initial={{
          key: '',
          title: s.editing?.title ?? '',
          parent_id: s.editing?.parent_id ?? NONE,
          path: s.editing?.path ?? '',
          component: s.editing?.component ?? NONE,
          icon: s.editing?.icon ?? NONE,
          permission: s.editing?.permission ?? NONE,
          sort_order: String(s.editing?.sort_order ?? 0),
          hidden: s.editing?.hidden ?? false,
        }}
        onSubmit={(v) =>
          s.editing
            ? update.mutateAsync({ id: s.editing.id, ...toBody(v) })
            : create.mutateAsync({ key: v.key as string, ...toBody(v) })
        }
      />
      <ConfirmDialog
        open={!!s.deleting}
        onOpenChange={(o) => !o && s.closeDelete()}
        title={t('menus.delete')}
        desc={t(
          s.deleting?.path ? 'menus.deleteDesc' : 'menus.deleteGroupDesc',
          { title: s.deleting?.title }
        )}
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
