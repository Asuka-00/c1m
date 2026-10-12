/** MES 实体通用表格。 */
import { useRef } from 'react'
import { AxiosError } from 'axios'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import {
  CopyPlus,
  Download,
  ListTree,
  MoreHorizontal,
  Plus,
  Upload,
} from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesEntity, type MesRow } from '@/lib/api/mes/common'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  ConfirmDialog,
  DataTable,
  RowActions,
  useCrudState,
  type Column,
  type ListParams,
} from '@/components/crud'
import { cellValue } from './cells'
import { EntityForm } from './entity-form'
import { entityLabel, fieldLabel, rowLabel, statusLabel } from './labels'
import { mesErrorMessage } from './required'
import { CELLS, ROW_RULES } from './row-rules'
import { useMesFilters } from './use-mes-filters'

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'outline'> = {
  active: 'default',
  draft: 'outline',
  inactive: 'secondary',
}

/** 版本状态徽标（draft / active / inactive）。 */
export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={STATUS_VARIANT[status] ?? 'outline'}>
      {statusLabel(status)}
    </Badge>
  )
}

/** 通用 MES 表格：分页 / 排序 / 搜索 / 筛选、CRUD 对话框、版本管理、
 *  xlsx 导入导出及每行的额外操作。 */
export function EntityTable({
  entity: e,
  params,
  fixed = {},
  extraActions,
  onOpenChildren,
}: {
  entity: MesEntity
  params: ListParams
  /** 固定筛选条件，同时作为新增行的预设值（如 {route_id}） */
  fixed?: Record<string, string>
  extraActions?: (r: MesRow) => React.ReactNode
  onOpenChildren?: (r: MesRow) => void
}) {
  const qc = useQueryClient()
  const tk = useTenantKey()
  const s = useCrudState<MesRow>()
  const fileRef = useRef<HTMLInputElement>(null)
  const hide = Object.keys(fixed)
  const filters = useMesFilters(e, hide)
  const query = { ...params.query, ...fixed }
  const list = useQuery({
    queryKey: ['mes', e.code, 'list', tk, query],
    queryFn: () => mesApi.list(e.code, query),
  })
  const invalidate = () => qc.invalidateQueries({ queryKey: ['mes', e.code] })
  const onErr = (err: unknown) => toast.error(mesErrorMessage(err, e))
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      s.editing
        ? mesApi.update(e.code, s.editing.id, body)
        : mesApi.create(e.code, body),
    onSuccess: () => {
      toast.success(t('mes.saved'))
      s.closeForm()
      invalidate()
    },
    onError: onErr,
  })
  const remove = useMutation({
    mutationFn: (r: MesRow) => mesApi.remove(e.code, r.id),
    onSuccess: () => {
      toast.success(t('mes.deleted'))
      s.closeDelete()
      invalidate()
    },
    onError: onErr,
  })
  const status = useMutation({
    mutationFn: ({ r, st }: { r: MesRow; st: string }) =>
      mesApi.setStatus(e.code, r.id, st),
    onSuccess: () => {
      toast.success(t('mes.statusChanged'))
      invalidate()
    },
    onError: onErr,
  })
  const newVersion = useMutation({
    mutationFn: (r: MesRow) => mesApi.newVersion(e.code, r.id),
    onSuccess: (r) => {
      toast.success(t('mes.versionCreated', { version: r.version }))
      invalidate()
    },
    onError: onErr,
  })
  const doImport = async (file: File | undefined) => {
    if (!file) return
    try {
      const r = await mesApi.importXlsx(e.code, file)
      toast.success(t('mes.imported', r))
      invalidate()
    } catch (err) {
      const d =
        err instanceof AxiosError
          ? (err.response?.data as {
              detail?: { errors?: { row: number; msg: string }[] }
            })
          : undefined
      const rows = d?.detail?.errors
      if (rows?.length)
        toast.error(t('mes.importFailed'), {
          description: rows
            .slice(0, 5)
            .map((x) => t('mes.importRow', x))
            .join('\n'),
        })
      else onErr(err)
    } finally {
      if (fileRef.current) fileRef.current.value = ''
    }
  }
  const editable = (r: MesRow) =>
    e.can_write && !e.readonly && (!e.versioned || r.status === 'draft')

  const columns: Column<MesRow>[] = [
    ...e.fields
      .filter((f) => f.list && !hide.includes(f.column))
      .map((f) => ({
        header: fieldLabel(e, f),
        sortKey: ['json', 'ref', 'text'].includes(f.type) ? undefined : f.name,
        cell: (r: MesRow) =>
          CELLS[e.code]?.[f.name]?.(r) ?? cellValue(e, r, f.name),
      })),
    ...(e.versioned
      ? [
          {
            header: t('mes.version'),
            sortKey: 'version',
            cell: (r: MesRow) => `v${r.version}`,
          },
          {
            header: t('common.status'),
            sortKey: 'status',
            cell: (r: MesRow) => <StatusBadge status={String(r.status)} />,
          },
        ]
      : []),
    ...(e.code === 'audit_log'
      ? [
          {
            header: t('mes.at'),
            sortKey: 'created_at',
            cell: (r: MesRow) => fmtDateTime(r.created_at as string),
          },
        ]
      : []),
    {
      header: '',
      className: 'w-0',
      cell: (r: MesRow) => (
        <RowActions
          onEdit={
            editable(r) && (ROW_RULES[e.code]?.edit?.(r) ?? true)
              ? () => s.openEdit(r)
              : undefined
          }
          onDelete={
            editable(r) && (ROW_RULES[e.code]?.remove?.(r) ?? true)
              ? () => s.openDelete(r)
              : undefined
          }
        >
          {extraActions?.(r)}
          {onOpenChildren && (
            <Button
              size='icon'
              variant='ghost'
              aria-label={t('mes.details')}
              title={t('mes.details')}
              onClick={() => onOpenChildren(r)}
            >
              <ListTree className='size-4' />
            </Button>
          )}
          {e.versioned && e.can_write && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  size='icon'
                  variant='ghost'
                  aria-label={t('mes.versionActions')}
                >
                  <MoreHorizontal className='size-4' />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align='end'>
                {r.status !== 'active' && (
                  <DropdownMenuItem
                    onClick={() => status.mutate({ r, st: 'active' })}
                  >
                    {t('mes.activate')}
                  </DropdownMenuItem>
                )}
                {r.status !== 'inactive' && (
                  <DropdownMenuItem
                    onClick={() => status.mutate({ r, st: 'inactive' })}
                  >
                    {t('mes.deactivate')}
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => newVersion.mutate(r)}>
                  <CopyPlus className='size-4' />
                  {t('mes.newVersion')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </RowActions>
      ),
    },
  ]

  const toolbar = (
    <div className='ms-auto flex flex-wrap items-center gap-2'>
      <Button
        variant='outline'
        size='sm'
        onClick={() => mesApi.exportXlsx(e.code).catch(onErr)}
      >
        <Download />
        {t('mes.export')}
      </Button>
      {e.can_write && !e.readonly && (
        <>
          <input
            ref={fileRef}
            type='file'
            accept='.xlsx'
            className='hidden'
            onChange={(ev) => doImport(ev.target.files?.[0])}
          />
          <Button
            variant='outline'
            size='sm'
            onClick={() => fileRef.current?.click()}
          >
            <Upload />
            {t('mes.import')}
          </Button>
          <Button size='sm' onClick={s.openCreate} data-testid='crud-new'>
            <Plus />
            {t('mes.new')}
          </Button>
        </>
      )}
    </div>
  )

  return (
    <>
      <DataTable
        rows={list.data?.data}
        total={list.data?.count}
        loading={list.isLoading}
        rowKey={(r) => r.id}
        params={params}
        filters={filters}
        columns={columns}
        toolbar={toolbar}
        empty={t('mes.empty', { entity: entityLabel(e.code) })}
      />
      <EntityForm
        entity={e}
        row={s.editing}
        open={s.formOpen}
        onOpenChange={(o) => !o && s.closeForm()}
        preset={fixed}
        pending={save.isPending}
        onSubmit={(body) => save.mutateAsync(body).catch(() => undefined)}
      />
      <ConfirmDialog
        open={!!s.deleting}
        onOpenChange={(o) => !o && s.closeDelete()}
        title={t('mes.deleteTitle', { entity: entityLabel(e.code) })}
        desc={t('mes.deleteDesc', {
          name: s.deleting ? rowLabel(s.deleting, e.label_field) : '',
        })}
        destructive
        confirmText={t('common.delete')}
        isLoading={remove.isPending}
        handleConfirm={() => s.deleting && remove.mutate(s.deleting)}
      />
    </>
  )
}
