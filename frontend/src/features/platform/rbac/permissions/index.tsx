/** 平台控制台 · 权限树：菜单与权限统一的树形表格（子项 / 编辑 / 删除、新增根权限）。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { ChevronDown, ChevronRight, Pencil, Plus, Trash2 } from 'lucide-react'
import { api, type PermNode } from '@/lib/api'
import { useApiMutation, useCan } from '@/lib/api/hooks'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ConfirmDialog, FormDialog, Page, type Values } from '@/components/crud'
import { IconButton, IconTooltip } from '@/components/icon-button'
import { StatusBadge } from '../status'
import { statusOptions } from '../status-options'
import { allIds, filterTree, nodeLabel as label } from '../tree'
import { TypeBadge } from '../type-badge'

/** 对话框状态：新增 / 编辑 菜单或权限。 */
type Edit =
  | { mode: 'menu'; node?: PermNode; parent?: PermNode }
  | { mode: 'perm'; node?: PermNode; parent?: PermNode }

const ANY = '_all'

/** 权限树页面（仅超级用户）。 */
export default function PermissionTreePage() {
  const writable = useCan()('roles:write')
  const [space, setSpace] = useState(ANY)
  const [type, setType] = useState(ANY)
  const [q, setQ] = useState('')
  const tree = useQuery({
    queryKey: ['permission-tree', 'page', space],
    queryFn: () => api.permissions.tree(space === ANY ? undefined : { space }),
  })
  const [open, setOpen] = useState<Set<string> | null>(null)
  const [edit, setEdit] = useState<Edit | null>(null)
  const [deleting, setDeleting] = useState<PermNode | null>(null)
  const keys = [['permission-tree'], ['menus'], ['roles'], ['tenant-roles']]
  const saveMenu = useApiMutation(
    (v: Values) => {
      const b = {
        title: v.title as string,
        path: (v.path as string) || null,
        icon: (v.icon as string) || null,
        component: (v.component as string) || null,
        permission: (v.permission as string) || null,
        sort_order: Number(v.sort_order) || 0,
        hidden: v.visible !== 'true',
        status: v.status as string,
        space: v.space as 'workspace' | 'platform',
      }
      return edit?.node
        ? api.menus.update(edit.node.id, b)
        : api.menus.create({
            ...b,
            key: v.key as string,
            parent_id: edit?.parent?.id ?? null,
          })
    },
    keys,
    t('rbac.saved')
  )
  const savePerm = useApiMutation(
    (v: Values) => {
      const b = {
        code: v.code as string,
        name: (v.name as string) || null,
        type: v.type as PermNode['type'],
        scope: v.scope as string,
        sort_order: Number(v.sort_order) || 0,
        status: v.status as string,
        description: (v.description as string) || null,
      }
      return edit?.node
        ? api.permissions.update(edit.node.id, b)
        : api.permissions.create({
            ...b,
            menu_id: edit?.parent?.kind === 'menu' ? edit.parent.id : null,
          })
    },
    keys,
    t('rbac.saved')
  )
  const remove = useApiMutation(
    (n: PermNode) =>
      n.kind === 'menu' ? api.menus.remove(n.id) : api.permissions.remove(n.id),
    keys,
    t('rbac.deleted')
  )
  const roots = tree.data ?? []
  const byType = (ns: PermNode[]): PermNode[] =>
    type === ANY
      ? ns
      : ns.flatMap((n) => {
          const children = byType(n.children)
          return n.type === type || children.length ? [{ ...n, children }] : []
        })
  const shown = byType(filterTree(roots, q))
  const filtering = !!q || type !== ANY
  const expanded = open ?? new Set(roots.map((n) => n.id))
  const rows: { n: PermNode; depth: number }[] = []
  const walk = (ns: PermNode[], depth: number) =>
    ns.forEach((n) => {
      rows.push({ n, depth })
      if (filtering || expanded.has(n.id)) walk(n.children, depth + 1)
    })
  walk(shown, 0)
  const toggle = (id: string) => {
    const s = new Set(expanded)
    if (s.has(id)) s.delete(id)
    else s.add(id)
    setOpen(s)
  }
  const e = edit?.node
  return (
    <Page
      title={t('rbac.treeTitle')}
      description={t('rbac.treeDesc')}
      actions={
        writable && (
          <Button onClick={() => setEdit({ mode: 'menu' })}>
            <Plus /> {t('rbac.newRoot')}
          </Button>
        )
      }
    >
      <div className='mb-3 flex flex-wrap items-center gap-2'>
        <Input
          className='h-9 w-64'
          placeholder={t('rbac.searchTree')}
          value={q}
          onChange={(x) => setQ(x.target.value)}
        />
        <Select value={space} onValueChange={setSpace}>
          <SelectTrigger
            className='max-w-72 min-w-40'
            aria-label={t('rbac.space')}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>{t('rbac.allSpaces')}</SelectItem>
            <SelectItem value='workspace'>
              {t('rbac.spaces.workspace')}
            </SelectItem>
            <SelectItem value='platform'>
              {t('rbac.spaces.platform')}
            </SelectItem>
          </SelectContent>
        </Select>
        <Select value={type} onValueChange={setType}>
          <SelectTrigger
            className='max-w-72 min-w-36'
            aria-label={t('rbac.type')}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>{t('rbac.allTypes')}</SelectItem>
            {['MENU', 'BUTTON', 'API'].map((x) => (
              <SelectItem key={x} value={x}>
                {x}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className='ms-auto flex gap-1'>
          <Button
            size='sm'
            variant='ghost'
            onClick={() => setOpen(new Set(allIds(roots)))}
          >
            {t('rbac.expandAll')}
          </Button>
          <Button size='sm' variant='ghost' onClick={() => setOpen(new Set())}>
            {t('rbac.collapseAll')}
          </Button>
        </div>
      </div>
      <div className='rounded-md border'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('common.name')}</TableHead>
              <TableHead>{t('rbac.code')}</TableHead>
              <TableHead>{t('rbac.type')}</TableHead>
              <TableHead>{t('rbac.path')}</TableHead>
              <TableHead className='w-16'>{t('rbac.sort')}</TableHead>
              <TableHead className='w-20'>{t('rbac.visible')}</TableHead>
              <TableHead className='w-20'>{t('common.status')}</TableHead>
              <TableHead className='w-32 text-end'>
                {t('rbac.actions')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tree.isLoading && (
              <TableRow>
                <TableCell colSpan={8} className='text-muted-foreground'>
                  {t('common.loading')}
                </TableCell>
              </TableRow>
            )}
            {!tree.isLoading && !rows.length && (
              <TableRow>
                <TableCell colSpan={8} className='text-muted-foreground'>
                  {t('common.noResults')}
                </TableCell>
              </TableRow>
            )}
            {rows.map(({ n, depth }) => (
              <TableRow key={n.id}>
                <TableCell>
                  <div
                    className='flex items-center gap-1'
                    style={{ paddingInlineStart: depth * 20 }}
                  >
                    {n.children.length ? (
                      <IconTooltip
                        label={
                          expanded.has(n.id)
                            ? t('common.collapse')
                            : t('common.expand')
                        }
                      >
                        <button
                          type='button'
                          className='text-muted-foreground'
                          aria-label={
                            expanded.has(n.id)
                              ? t('common.collapse')
                              : t('common.expand')
                          }
                          onClick={() => toggle(n.id)}
                        >
                          {filtering || expanded.has(n.id) ? (
                            <ChevronDown className='size-4' />
                          ) : (
                            <ChevronRight className='size-4' />
                          )}
                        </button>
                      </IconTooltip>
                    ) : (
                      <span className='w-4' />
                    )}
                    <span className={n.kind === 'perm' ? '' : 'font-medium'}>
                      {label(n)}
                    </span>
                    {depth === 0 && n.space && (
                      <Badge variant='outline' className='ms-1 text-[10px]'>
                        {t(`rbac.spaces.${n.space}`)}
                      </Badge>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <code className='text-xs'>{n.code}</code>
                </TableCell>
                <TableCell>
                  {n.kind !== 'group' && <TypeBadge type={n.type} />}
                </TableCell>
                <TableCell className='text-muted-foreground'>
                  {n.path ?? ''}
                </TableCell>
                <TableCell>{n.kind === 'group' ? '' : n.sort_order}</TableCell>
                <TableCell>
                  {n.kind === 'menu' &&
                    (n.visible ? t('rbac.shown') : t('rbac.hidden'))}
                </TableCell>
                <TableCell>
                  {n.kind !== 'group' && (
                    <StatusBadge active={n.status !== 'disabled'} />
                  )}
                </TableCell>
                <TableCell>
                  {writable && n.kind !== 'group' && (
                    <div className='flex justify-end gap-1'>
                      {n.kind === 'menu' && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button size='sm' variant='ghost'>
                              <Plus className='size-4' /> {t('rbac.child')}
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align='end'>
                            <DropdownMenuItem
                              onClick={() =>
                                setEdit({ mode: 'menu', parent: n })
                              }
                            >
                              {t('rbac.childMenu')}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() =>
                                setEdit({ mode: 'perm', parent: n })
                              }
                            >
                              {t('rbac.childPerm')}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                      <IconButton
                        label={t('common.edit')}
                        variant='ghost'
                        onClick={() =>
                          setEdit({
                            mode: n.kind === 'menu' ? 'menu' : 'perm',
                            node: n,
                          })
                        }
                      >
                        <Pencil className='size-4' />
                      </IconButton>
                      <IconButton
                        label={t('common.delete')}
                        variant='ghost'
                        onClick={() => setDeleting(n)}
                      >
                        <Trash2 className='size-4 text-destructive' />
                      </IconButton>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <FormDialog
        open={edit?.mode === 'menu'}
        onOpenChange={(o) => !o && setEdit(null)}
        title={
          e
            ? t('rbac.editMenu')
            : edit?.parent
              ? t('rbac.newChildMenu', { parent: label(edit.parent) })
              : t('rbac.newRoot')
        }
        fields={[
          {
            name: 'key',
            label: t('rbac.menuKey'),
            required: true,
            readOnly: !!e,
          },
          { name: 'title', label: t('common.name'), required: true },
          { name: 'path', label: t('rbac.path'), placeholder: '/xxx' },
          { name: 'icon', label: t('rbac.icon') },
          { name: 'component', label: t('rbac.component') },
          { name: 'permission', label: t('rbac.menuPerm') },
          { name: 'sort_order', label: t('rbac.sort'), type: 'number' },
          {
            name: 'space',
            label: t('rbac.space'),
            type: 'radio',
            options: [
              { value: 'workspace', label: t('rbac.spaces.workspace') },
              { value: 'platform', label: t('rbac.spaces.platform') },
            ],
          },
          {
            name: 'status',
            label: t('common.status'),
            type: 'radio',
            options: statusOptions(),
          },
          {
            name: 'visible',
            label: t('rbac.visible'),
            type: 'radio',
            options: [
              { value: 'true', label: t('rbac.shown') },
              { value: 'false', label: t('rbac.hidden') },
            ],
          },
        ]}
        initial={{
          key: e?.key ?? '',
          title: e?.name ?? '',
          path: e?.path ?? '',
          icon: e?.icon ?? '',
          component: e?.component ?? '',
          permission: e?.code ?? '',
          sort_order: String(e?.sort_order ?? 0),
          space: e?.space ?? edit?.parent?.space ?? 'workspace',
          visible: String(e?.visible ?? true),
          status: e?.status ?? 'active',
        }}
        pending={saveMenu.isPending}
        onSubmit={(v) => saveMenu.mutateAsync(v)}
      />
      <FormDialog
        open={edit?.mode === 'perm'}
        onOpenChange={(o) => !o && setEdit(null)}
        title={
          e
            ? t('permissions.edit')
            : t('rbac.newChildPerm', {
                parent: edit?.parent ? label(edit.parent) : '',
              })
        }
        fields={[
          { name: 'code', label: t('permissions.codeLabel'), required: true },
          { name: 'name', label: t('common.name') },
          {
            name: 'type',
            label: t('rbac.type'),
            type: 'radio',
            options: ['MENU', 'BUTTON', 'API'].map((x) => ({
              value: x,
              label: x,
            })),
          },
          {
            name: 'scope',
            label: t('permissions.scope'),
            type: 'radio',
            options: [
              { value: 'platform', label: t('permissions.scopes.platform') },
              { value: 'tenant', label: t('permissions.scopes.tenant') },
            ],
          },
          { name: 'sort_order', label: t('rbac.sort'), type: 'number' },
          {
            name: 'status',
            label: t('common.status'),
            type: 'radio',
            options: statusOptions(),
          },
          { name: 'description', label: t('common.description') },
        ]}
        initial={{
          code: e?.code ?? '',
          name: e?.name && e.name !== e.code ? e.name : '',
          type: e?.type ?? 'BUTTON',
          scope:
            e?.scope ??
            (edit?.parent?.space === 'platform' ? 'platform' : 'tenant'),
          sort_order: String(e?.sort_order ?? 0),
          status: e?.status ?? 'active',
          description: e?.description ?? '',
        }}
        pending={savePerm.isPending}
        onSubmit={(v) => savePerm.mutateAsync(v)}
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t('rbac.deleteNode')}
        desc={
          deleting?.kind === 'menu'
            ? t('rbac.deleteMenuDesc', { name: label(deleting) })
            : t('permissions.deleteDesc', { code: deleting?.code })
        }
        destructive
        confirmText={t('common.delete')}
        handleConfirm={() =>
          deleting &&
          remove.mutate(deleting, { onSuccess: () => setDeleting(null) })
        }
      />
    </Page>
  )
}
