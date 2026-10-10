import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import {
  ArrowDown,
  ArrowUp,
  ChevronRight,
  CornerDownRight,
  GitBranch,
  List,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  Undo2,
  Workflow,
} from 'lucide-react'
import { toast } from 'sonner'
import { errorMessage } from '@/lib/api/client'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, reorderRouteSteps, type MesRow } from '@/lib/api/mes'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/crud'
import { ChildTable } from './child-table'
import { EntityForm } from './entity-form'
import { StatusBadge } from './entity-table'
import { enumLabel } from './labels'
import { useMesEntity } from './use-mes-meta'

const stepsKey = (tk: string, routeId: string) => [
  'mes',
  'route_step',
  'flow',
  tk,
  routeId,
]

function useSteps(routeId: string | null) {
  const tk = useTenantKey()
  return useQuery({
    queryKey: stepsKey(tk, routeId ?? ''),
    queryFn: () =>
      mesApi.list('route_step', {
        route_id: routeId!,
        page_size: 100,
        sort_by: 'seq',
      }),
    enabled: !!routeId,
  })
}

/** Route editor: ordered steps as a flow (sub-route calls expandable, rework
 *  and branch links shown), reorder / add / edit / delete on draft versions. */
export function RouteEditor({ row }: { row: MesRow }) {
  const [mode, setMode] = useState<'flow' | 'list'>('flow')
  const { entity: stepEntity } = useMesEntity('route_step')
  const { entity: routeEntity } = useMesEntity('route')
  const qc = useQueryClient()
  const tk = useTenantKey()
  const steps = useSteps(row.id)
  const [editing, setEditing] = useState<MesRow | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<MesRow | null>(null)
  const [openRes, setOpenRes] = useState<string | null>(null)
  const editable = row.status === 'draft' && !!routeEntity?.can_write
  const list = steps.data?.data ?? []
  const refresh = () =>
    qc.invalidateQueries({ queryKey: ['mes', 'route_step'] })
  const onErr = (e: unknown) => toast.error(errorMessage(e))
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      editing
        ? mesApi.update('route_step', editing.id, body)
        : mesApi.create('route_step', body),
    onSuccess: () => {
      toast.success(t('mes.saved'))
      setEditing(null)
      setCreating(false)
      refresh()
    },
    onError: onErr,
  })
  const remove = useMutation({
    mutationFn: (r: MesRow) => mesApi.remove('route_step', r.id),
    onSuccess: () => {
      setDeleting(null)
      refresh()
    },
    onError: onErr,
  })
  const move = useMutation({
    mutationFn: (ids: string[]) => reorderRouteSteps(row.id, ids),
    onSuccess: (r) =>
      qc.setQueryData(stepsKey(tk, row.id), {
        data: r.data,
        count: r.data.length,
      }),
    onError: onErr,
  })
  const swap = (i: number, j: number) => {
    const ids = list.map((s) => s.id)
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    move.mutate(ids)
  }
  const nextSeq = ((list[list.length - 1]?.seq as number | undefined) ?? 0) + 10
  if (!stepEntity) return null
  return (
    <div className='space-y-3 pt-2' data-testid='route-editor'>
      <div className='flex flex-wrap items-center gap-2'>
        <StatusBadge status={String(row.status)} />
        <span className='text-sm text-muted-foreground'>
          {editable ? t('mes.routeDraftHint') : t('mes.routeLockedHint')}
        </span>
        <div className='ms-auto flex gap-2'>
          <Button
            size='sm'
            variant='outline'
            onClick={() => setMode(mode === 'flow' ? 'list' : 'flow')}
          >
            {mode === 'flow' ? <List /> : <Workflow />}
            {mode === 'flow' ? t('mes.listView') : t('mes.flowView')}
          </Button>
          {editable && mode === 'flow' && (
            <Button size='sm' onClick={() => setCreating(true)}>
              <Plus />
              {t('mes.addStep')}
            </Button>
          )}
        </div>
      </div>
      {mode === 'list' ? (
        <ChildTable code='route_step' parentCode='route' parentId={row.id} />
      ) : steps.isLoading ? (
        <Loader2 className='mx-auto animate-spin' />
      ) : !list.length ? (
        <p className='rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground'>
          {t('mes.noSteps')}
        </p>
      ) : (
        <ol className='space-y-0'>
          {list.map((s, i) => (
            <li key={s.id}>
              <StepCard
                step={s}
                editable={editable}
                first={i === 0}
                last={i === list.length - 1}
                onUp={() => swap(i, i - 1)}
                onDown={() => swap(i, i + 1)}
                onEdit={() => setEditing(s)}
                onDelete={() => setDeleting(s)}
                resOpen={openRes === s.id}
                onToggleRes={() => setOpenRes(openRes === s.id ? null : s.id)}
              />
              {i < list.length - 1 && (
                <div className='ms-7 h-4 border-s-2 border-dashed border-muted-foreground/40' />
              )}
            </li>
          ))}
        </ol>
      )}
      <EntityForm
        entity={stepEntity}
        row={editing}
        open={creating || !!editing}
        onOpenChange={(o) => {
          if (!o) {
            setCreating(false)
            setEditing(null)
          }
        }}
        preset={{ route_id: row.id }}
        defaults={{ seq: nextSeq }}
        pending={save.isPending}
        onSubmit={(b) => save.mutateAsync(b).catch(() => undefined)}
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t('mes.deleteTitle', { entity: t('mes.entity.route_step') })}
        desc={t('mes.deleteDesc', { name: String(deleting?.seq ?? '') })}
        destructive
        confirmText={t('common.delete')}
        handleConfirm={() => deleting && remove.mutate(deleting)}
      />
    </div>
  )
}

function StepCard({
  step: s,
  editable,
  first,
  last,
  onUp,
  onDown,
  onEdit,
  onDelete,
  resOpen,
  onToggleRes,
}: {
  step: MesRow
  editable: boolean
  first: boolean
  last: boolean
  onUp: () => void
  onDown: () => void
  onEdit: () => void
  onDelete: () => void
  resOpen: boolean
  onToggleRes: () => void
}) {
  const [subOpen, setSubOpen] = useState(false)
  const isSub = s.step_type === 'sub_route'
  return (
    <div
      className={cn(
        'rounded-lg border bg-card p-3',
        isSub && 'border-primary/50 bg-primary/5'
      )}
    >
      <div className='flex flex-wrap items-center gap-2'>
        <span className='flex size-10 shrink-0 items-center justify-center rounded-full bg-muted font-mono text-sm font-semibold'>
          {String(s.seq)}
        </span>
        <div className='min-w-0 flex-1'>
          <div className='flex flex-wrap items-center gap-2 font-medium'>
            {isSub ? (
              <button
                type='button'
                className='flex items-center gap-1 text-primary'
                onClick={() => setSubOpen(!subOpen)}
              >
                <ChevronRight
                  className={cn(
                    'size-4 transition-transform',
                    subOpen && 'rotate-90'
                  )}
                />
                {String(s.sub_route_label ?? '')}
              </button>
            ) : (
              String(s.operation_label ?? '')
            )}
            <Badge variant='outline'>
              {enumLabel('step_type', String(s.step_type))}
            </Badge>
            {!!s.is_optional && (
              <Badge variant='secondary'>
                {t('mes.field.route_step.is_optional')}
              </Badge>
            )}
          </div>
          <div className='mt-1 flex flex-wrap gap-3 text-xs text-muted-foreground'>
            {!!s.rework_route_id && (
              <span className='flex items-center gap-1'>
                <Undo2 className='size-3.5' />
                {t('mes.reworkTo', { route: String(s.rework_route_label) })}
              </span>
            )}
            {s.branch_to_seq != null && (
              <span className='flex items-center gap-1'>
                <GitBranch className='size-3.5' />
                {t('mes.branchTo', {
                  cond: String(s.branch_condition ?? ''),
                  seq: String(s.branch_to_seq),
                })}
              </span>
            )}
            {!!s.note && <span>{String(s.note)}</span>}
          </div>
        </div>
        <div className='flex items-center gap-0.5'>
          <Button size='sm' variant='ghost' onClick={onToggleRes}>
            {t('mes.resources')}
          </Button>
          {editable && (
            <>
              <Button
                size='icon'
                variant='ghost'
                disabled={first}
                onClick={onUp}
                aria-label={t('mes.moveUp')}
              >
                <ArrowUp className='size-4' />
              </Button>
              <Button
                size='icon'
                variant='ghost'
                disabled={last}
                onClick={onDown}
                aria-label={t('mes.moveDown')}
              >
                <ArrowDown className='size-4' />
              </Button>
              <Button
                size='icon'
                variant='ghost'
                onClick={onEdit}
                aria-label={t('common.edit')}
              >
                <Pencil className='size-4' />
              </Button>
              <Button
                size='icon'
                variant='ghost'
                onClick={onDelete}
                aria-label={t('common.delete')}
              >
                <Trash2 className='size-4 text-destructive' />
              </Button>
            </>
          )}
        </div>
      </div>
      {isSub && subOpen && <SubSteps routeId={String(s.sub_route_id)} />}
      {resOpen && (
        <div className='mt-3 border-t pt-3'>
          <ChildTable
            code='step_resource'
            parentCode='route_step'
            parentId={s.id}
          />
        </div>
      )}
    </div>
  )
}

function SubSteps({ routeId }: { routeId: string }) {
  const { data, isLoading } = useSteps(routeId)
  if (isLoading) return <Loader2 className='ms-12 mt-2 animate-spin' />
  return (
    <ol className='ms-12 mt-2 space-y-1'>
      {(data?.data ?? []).map((x) => (
        <li key={x.id} className='flex items-center gap-2 text-sm'>
          <CornerDownRight className='size-4 text-muted-foreground' />
          <span className='font-mono text-xs'>{String(x.seq)}</span>
          {String(x.operation_label ?? x.sub_route_label ?? '')}
        </li>
      ))}
    </ol>
  )
}
