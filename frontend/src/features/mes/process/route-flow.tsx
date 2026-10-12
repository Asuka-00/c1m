import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import dagre from '@dagrejs/dagre'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  ArrowDown,
  ArrowUp,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  X,
} from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { reorderRouteSteps } from '@/lib/api/mes/process'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/crud'
import { EntityForm } from '@/features/mes/common/entity-form'
import { StatusBadge } from '@/features/mes/common/entity-table'
import { enumLabel } from '@/features/mes/common/labels'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'

type StepData = { step: MesRow; selected: boolean; current?: boolean }
type RefData = {
  label: string
  kind: 'sub' | 'rework'
  steps?: MesRow[]
  linked: boolean
}
type TermData = { label: string }

const W = 260
const H = 72

function StepNode({ data }: NodeProps<Node<StepData>>) {
  const s = data.step
  const sub = s.step_type === 'sub_route'
  return (
    <div
      className={cn(
        'rounded-lg border-2 bg-card px-3 py-2 text-xs shadow-sm',
        sub ? 'border-primary/60 bg-primary/5' : 'border-border',
        data.selected && 'ring-2 ring-primary',
        data.current &&
          'border-amber-500 bg-amber-50 ring-4 ring-amber-400/60 dark:bg-amber-950'
      )}
      style={{ width: W }}
      data-testid={`step-${String(s.seq)}`}
    >
      <Handle type='target' position={Position.Top} />
      <div className='flex items-center gap-2'>
        <span className='rounded bg-muted px-1.5 font-mono font-semibold'>
          {String(s.seq)}
        </span>
        <span className='truncate font-medium'>
          {String((sub ? s.sub_route_label : s.operation_label) ?? '')}
        </span>
      </div>
      <div className='mt-1 flex gap-1'>
        <Badge variant='outline' className='text-[10px]'>
          {enumLabel('step_type', String(s.step_type))}
        </Badge>
        {data.current && (
          <Badge className='bg-amber-500 text-[10px] text-white'>
            {t('mes.currentStep')}
          </Badge>
        )}
        {!!s.is_optional && (
          <Badge variant='secondary' className='text-[10px]'>
            {t('mes.field.route_step.is_optional')}
          </Badge>
        )}
      </div>
      <Handle type='source' position={Position.Bottom} />
      <Handle type='source' id='side' position={Position.Right} />
      <Handle type='target' id='side-in' position={Position.Left} />
    </div>
  )
}

function RefNode({ data }: NodeProps<Node<RefData>>) {
  return (
    <div
      className={cn(
        'rounded-lg border-2 border-dashed px-3 py-2 text-xs',
        data.kind === 'rework'
          ? 'border-destructive/60 bg-destructive/5'
          : 'border-primary/60 bg-primary/5',
        !data.linked && 'opacity-60'
      )}
      style={{ width: W }}
    >
      <Handle type='target' position={Position.Left} />
      <div className='font-medium'>
        {data.kind === 'rework' ? t('mes.reworkRoute') : t('mes.subRoute')}:{' '}
        {data.label}
      </div>
      {data.steps && (
        <ol className='mt-1 space-y-0.5 text-muted-foreground'>
          {data.steps.map((x) => (
            <li key={x.id}>
              {String(x.seq)} ·{' '}
              {String(x.operation_label ?? x.sub_route_label ?? '')}
            </li>
          ))}
        </ol>
      )}
      <Handle type='source' position={Position.Right} />
    </div>
  )
}

function TermNode({ data }: NodeProps<Node<TermData>>) {
  return (
    <div className='rounded-full border-2 bg-muted px-4 py-1 text-xs font-semibold'>
      <Handle type='target' position={Position.Top} />
      {data.label}
      <Handle type='source' position={Position.Bottom} />
    </div>
  )
}

const nodeTypes = { step: StepNode, ref: RefNode, term: TermNode }

function layout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 50 })
  g.setDefaultEdgeLabel(() => ({}))
  for (const n of nodes) {
    const h =
      n.type === 'ref'
        ? H + 16 * ((n.data as RefData).steps?.length ?? 0)
        : n.type === 'term'
          ? 32
          : H
    g.setNode(n.id, { width: n.type === 'term' ? 100 : W, height: h })
  }
  // only the main chain + calls shape the layout; loops are drawn on top
  for (const e of edges) if (e.data?.layout) g.setEdge(e.source, e.target)
  dagre.layout(g)
  return nodes.map((n) => {
    const p = g.node(n.id)
    return { ...n, position: { x: p.x - p.width / 2, y: p.y - p.height / 2 } }
  })
}

function useRouteSteps(routeId: string | undefined) {
  const tk = useTenantKey()
  return useQuery({
    queryKey: ['mes', 'route_step', 'flow', tk, routeId],
    queryFn: () =>
      mesApi.list('route_step', {
        route_id: routeId!,
        page_size: 100,
        sort_by: 'seq',
      }),
    enabled: !!routeId,
  })
}

/** Visual route editor (React Flow + dagre auto-layout): steps in order, main
 *  flow, sub-route calls, rework loops and labelled branches. Draft: connect a
 *  step to another step (branch) or to a rework route, delete edges, add /
 *  edit / delete / reorder steps in the side panel. Active/Inactive: read-only. */
export function RouteFlow({
  row,
  readOnly = false,
  highlight = null,
}: {
  row: MesRow
  readOnly?: boolean
  /** route step id to highlight (e.g. a lot's current step) */
  highlight?: string | null
}) {
  const qc = useQueryClient()
  const tk = useTenantKey()
  const { entity: stepEntity } = useMesEntity('route_step')
  const { entity: routeEntity } = useMesEntity('route')
  const editable =
    !readOnly && row.status === 'draft' && !!routeEntity?.can_write
  const steps = useRouteSteps(row.id)
  const list = useMemo(() => steps.data?.data ?? [], [steps.data])
  const subIds = [
    ...new Set(list.map((s) => s.sub_route_id).filter(Boolean)),
  ] as string[]
  const subs = useQuery({
    queryKey: ['mes', 'route_step', 'flow-subs', tk, subIds],
    queryFn: async () =>
      Object.fromEntries(
        await Promise.all(
          subIds.map(async (id) => [
            id,
            (
              await mesApi.list('route_step', {
                route_id: id,
                page_size: 100,
                sort_by: 'seq',
              })
            ).data,
          ])
        )
      ) as Record<string, MesRow[]>,
    enabled: subIds.length > 0,
  })
  const reworks = useQuery({
    queryKey: ['mes', 'route', 'rework-options', tk],
    queryFn: () =>
      mesApi.list('route', {
        route_type: 'rework',
        status: 'active',
        page_size: 100,
      }),
    enabled: editable,
  })
  const [selected, setSelected] = useState<string | null>(null)
  const [editing, setEditing] = useState<MesRow | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<MesRow | null>(null)
  const [branch, setBranch] = useState<{
    from: MesRow
    to: MesRow
    cond: string
  } | null>(null)

  const refresh = () =>
    qc.invalidateQueries({ queryKey: ['mes', 'route_step'] })
  const onErr = (e: unknown) => toast.error(mesErrorMessage(e, stepEntity))
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      mesApi.update('route_step', id, body),
    onSuccess: refresh,
    onError: onErr,
  })
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
      setSelected(null)
      refresh()
    },
    onError: onErr,
  })
  const move = useMutation({
    mutationFn: (ids: string[]) => reorderRouteSteps(row.id, ids),
    onSuccess: refresh,
    onError: onErr,
  })

  const { nodes, edges } = useMemo(() => {
    const ns: Node[] = [
      {
        id: 'start',
        type: 'term',
        position: { x: 0, y: 0 },
        data: { label: t('mes.flowStart') },
      },
      {
        id: 'end',
        type: 'term',
        position: { x: 0, y: 0 },
        data: { label: t('mes.flowEnd') },
      },
    ]
    const es: Edge[] = []
    const bySeq = new Map(list.map((s) => [Number(s.seq), s]))
    const arrow = { type: MarkerType.ArrowClosed }
    let prev = 'start'
    const reworkSeen = new Set<string>()
    for (const s of list) {
      const id = `s-${s.id}`
      ns.push({
        id,
        type: 'step',
        position: { x: 0, y: 0 },
        data: {
          step: s,
          selected: selected === s.id,
          current: highlight === s.id,
        },
      })
      es.push({
        id: `m-${prev}-${id}`,
        source: prev,
        target: id,
        markerEnd: arrow,
        data: { layout: true, kind: 'main' },
      })
      prev = id
      if (s.step_type === 'sub_route' && s.sub_route_id) {
        const sid = `sub-${s.id}`
        ns.push({
          id: sid,
          type: 'ref',
          position: { x: 0, y: 0 },
          data: {
            label: String(s.sub_route_label),
            kind: 'sub',
            steps: subs.data?.[String(s.sub_route_id)] ?? [],
            linked: true,
          },
        })
        es.push({
          id: `call-${s.id}`,
          source: id,
          sourceHandle: 'side',
          target: sid,
          label: t('mes.edgeCall'),
          animated: true,
          markerEnd: arrow,
          style: { strokeDasharray: '6 4' },
          data: { layout: true, kind: 'call' },
        })
        es.push({
          id: `ret-${s.id}`,
          source: sid,
          target: id,
          targetHandle: 'side-in',
          label: t('mes.edgeReturn'),
          markerEnd: arrow,
          style: { strokeDasharray: '6 4' },
          data: { kind: 'return' },
        })
      }
      if (s.rework_route_id) {
        const rid = `rw-${String(s.rework_route_id)}`
        if (!reworkSeen.has(rid)) {
          reworkSeen.add(rid)
          ns.push({
            id: rid,
            type: 'ref',
            position: { x: 0, y: 0 },
            data: {
              label: String(s.rework_route_label),
              kind: 'rework',
              linked: true,
            },
          })
        }
        es.push({
          id: `rw-${s.id}`,
          source: id,
          sourceHandle: 'side',
          target: rid,
          label: t('mes.edgeRework'),
          markerEnd: arrow,
          style: { stroke: 'var(--destructive)', strokeDasharray: '4 3' },
          data: { layout: true, kind: 'rework', step: s },
        })
        es.push({
          id: `rwb-${s.id}`,
          source: rid,
          target: id,
          targetHandle: 'side-in',
          markerEnd: arrow,
          style: {
            stroke: 'var(--destructive)',
            strokeDasharray: '4 3',
            opacity: 0.5,
          },
          data: { kind: 'return' },
        })
      }
      if (s.branch_to_seq != null && bySeq.has(Number(s.branch_to_seq))) {
        es.push({
          id: `br-${s.id}`,
          source: id,
          sourceHandle: 'side',
          target: `s-${bySeq.get(Number(s.branch_to_seq))!.id}`,
          targetHandle: 'side-in',
          label: String(s.branch_condition ?? ''),
          labelStyle: { fill: 'var(--chart-1, #d97706)', fontWeight: 600 },
          markerEnd: arrow,
          style: { stroke: '#d97706', strokeWidth: 2 },
          type: 'smoothstep',
          data: { kind: 'branch', step: s },
        })
      }
    }
    es.push({
      id: `m-${prev}-end`,
      source: prev,
      target: 'end',
      markerEnd: arrow,
      data: { layout: true, kind: 'main' },
    })
    // draft: unlinked active rework routes are connect targets
    if (editable)
      for (const r of reworks.data?.data ?? []) {
        const rid = `rw-${r.id}`
        if (!reworkSeen.has(rid))
          ns.push({
            id: rid,
            type: 'ref',
            position: { x: 0, y: 0 },
            data: {
              label: `${r.code} v${r.version}`,
              kind: 'rework',
              linked: false,
            },
          })
      }
    return {
      nodes: layout(ns, es),
      edges: es.map((e) => ({
        ...e,
        deletable:
          editable && ['branch', 'rework'].includes(String(e.data?.kind)),
      })),
    }
  }, [list, subs.data, reworks.data, editable, selected, highlight])

  const stepOf = (nodeId: string) => list.find((s) => `s-${s.id}` === nodeId)
  const onConnect = (c: Connection) => {
    const from = stepOf(c.source)
    if (!from || !editable) return
    if (c.target.startsWith('rw-')) {
      patch.mutate({
        id: from.id,
        body: { rework_route_id: c.target.slice(3) },
      })
      return
    }
    const to = stepOf(c.target)
    if (to && to.id !== from.id)
      setBranch({ from, to, cond: String(from.branch_condition ?? '') })
  }
  const onEdgesDelete = (deleted: Edge[]) => {
    for (const e of deleted) {
      const s = e.data?.step as MesRow | undefined
      if (!s) continue
      if (e.data?.kind === 'branch')
        patch.mutate({
          id: s.id,
          body: { branch_condition: null, branch_to_seq: null },
        })
      if (e.data?.kind === 'rework')
        patch.mutate({ id: s.id, body: { rework_route_id: null } })
    }
  }
  const sel = list.find((s) => s.id === selected) ?? null
  const idx = sel ? list.indexOf(sel) : -1
  const swap = (i: number, j: number) => {
    const ids = list.map((s) => s.id)
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    move.mutate(ids)
  }
  const nextSeq = ((list[list.length - 1]?.seq as number | undefined) ?? 0) + 10
  if (!stepEntity) return null

  return (
    <div className='space-y-2 pt-2' data-testid='route-flow'>
      <div className='flex flex-wrap items-center gap-2'>
        <StatusBadge status={String(row.status)} />
        <span className='text-sm text-muted-foreground'>
          {readOnly
            ? t('mes.lotFlowHint')
            : editable
              ? t('mes.flowDraftHint')
              : t('mes.routeLockedHint')}
        </span>
        {editable && (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setCreating(true)}
          >
            <Plus />
            {t('mes.addStep')}
          </Button>
        )}
      </div>
      <div className='relative h-[68vh] rounded-md border'>
        {steps.isLoading ? (
          <Loader2 className='m-auto mt-20 animate-spin' />
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            nodesDraggable={false}
            nodesConnectable={editable}
            onConnect={onConnect}
            onEdgesDelete={onEdgesDelete}
            deleteKeyCode={editable ? ['Backspace', 'Delete'] : null}
            onNodeClick={(_, n) =>
              setSelected(n.id.startsWith('s-') ? n.id.slice(2) : null)
            }
            onPaneClick={() => setSelected(null)}
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
        {sel && (
          <aside
            className='absolute end-2 top-2 z-10 w-72 space-y-2 rounded-md border bg-background p-3 text-sm shadow-lg'
            data-testid='step-panel'
          >
            <div className='flex items-center justify-between'>
              <span className='font-semibold'>
                {t('mes.entity.route_step')} {String(sel.seq)}
              </span>
              <Button
                size='icon'
                variant='ghost'
                className='size-7'
                onClick={() => setSelected(null)}
                aria-label={t('common.close')}
              >
                <X className='size-4' />
              </Button>
            </div>
            <dl className='space-y-1 text-xs'>
              {(['operation', 'sub_route', 'rework_route'] as const).map((k) =>
                sel[`${k}_label`] ? (
                  <div key={k} className='flex gap-2'>
                    <dt className='text-muted-foreground'>
                      {t(`mes.field.route_step.${k}`)}
                    </dt>
                    <dd>{String(sel[`${k}_label`])}</dd>
                  </div>
                ) : null
              )}
              {sel.branch_to_seq != null && (
                <div className='flex gap-2'>
                  <dt className='text-muted-foreground'>
                    {t('mes.field.route_step.branch_condition')}
                  </dt>
                  <dd>
                    {String(sel.branch_condition)} → {String(sel.branch_to_seq)}
                  </dd>
                </div>
              )}
            </dl>
            {editable && (
              <div className='flex flex-wrap gap-1'>
                <Button
                  size='sm'
                  variant='outline'
                  onClick={() => setEditing(sel)}
                >
                  <Pencil />
                  {t('common.edit')}
                </Button>
                <Button
                  size='icon'
                  variant='outline'
                  disabled={idx <= 0}
                  onClick={() => swap(idx, idx - 1)}
                  aria-label={t('mes.moveUp')}
                >
                  <ArrowUp />
                </Button>
                <Button
                  size='icon'
                  variant='outline'
                  disabled={idx >= list.length - 1}
                  onClick={() => swap(idx, idx + 1)}
                  aria-label={t('mes.moveDown')}
                >
                  <ArrowDown />
                </Button>
                <Button
                  size='icon'
                  variant='outline'
                  onClick={() => setDeleting(sel)}
                  aria-label={t('common.delete')}
                >
                  <Trash2 className='text-destructive' />
                </Button>
              </div>
            )}
          </aside>
        )}
      </div>
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
      <Dialog open={!!branch} onOpenChange={(o) => !o && setBranch(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('mes.branchDialog', {
                from: String(branch?.from.seq ?? ''),
                to: String(branch?.to.seq ?? ''),
              })}
            </DialogTitle>
          </DialogHeader>
          <div className='space-y-1.5'>
            <Label htmlFor='br-cond'>
              {t('mes.field.route_step.branch_condition')}
            </Label>
            <Input
              id='br-cond'
              value={branch?.cond ?? ''}
              onChange={(e) =>
                branch && setBranch({ ...branch, cond: e.target.value })
              }
            />
            <p className='text-xs text-muted-foreground'>
              {t('mes.help.route_step.branch_condition')}
            </p>
          </div>
          <DialogFooter>
            <Button variant='outline' onClick={() => setBranch(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              disabled={!branch?.cond.trim()}
              onClick={() => {
                if (!branch) return
                patch.mutate({
                  id: branch.from.id,
                  body: {
                    branch_condition: branch.cond.trim(),
                    branch_to_seq: branch.to.seq,
                  },
                })
                setBranch(null)
              }}
            >
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
