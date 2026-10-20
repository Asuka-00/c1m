/** 路线可视化编辑器。 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from 'react'
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query'
import { t } from '@/i18n'
import {
  applyNodeChanges,
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  ArrowDown,
  ArrowUp,
  LayoutTemplate,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  X,
} from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import {
  reorderRouteSteps,
  saveRouteLayout,
  type StepLayout,
} from '@/lib/api/mes/process'
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
import { IconButton } from '@/components/icon-button'
import { EntityForm } from '@/features/mes/common/entity-form'
import { StatusBadge } from '@/features/mes/common/entity-table'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'
import {
  buildGraph,
  GRID,
  H,
  insertIndexAt,
  layoutOf,
  mainEdgeId,
  stepIdOf,
  stepNodeId,
  W,
} from './flow/graph'
import { RefNode, StepNode, TermNode } from './flow/nodes'
import { Palette, PALETTE_MIME, type PaletteItem } from './flow/palette'

const nodeTypes = { step: StepNode, ref: RefNode, term: TermNode }

type Branch = { from: MesRow; to: MesRow; cond: string }

function useRouteSteps(routeId: string | undefined) {
  const tk = useTenantKey()
  const queryKey: QueryKey = ['mes', 'route_step', 'flow', tk, routeId]
  const query = useQuery({
    queryKey,
    queryFn: () =>
      mesApi.list('route_step', {
        route_id: routeId!,
        page_size: 100,
        sort_by: 'seq',
      }),
    enabled: !!routeId,
  })
  return { query, queryKey }
}

const snap = (v: number) => Math.round(v / GRID) * GRID

/** 可视化路线编辑器（React Flow + dagre 自动布局）：按顺序展示工步、主流程、
 *  子路线调用、返工回路与带标签的分支。草稿：节点可自由拖动（位置随路线保存），
 *  从左侧面板把工序 / 子流程拖进画布添加工步，拖到连线上即插入该位置，
 *  拖动已有工步到另一段连线上调整顺序；把工步连接点拖到另一工步（分支）或返工路线，
 *  拖动连线端点改接、Delete 删除；侧栏新增 / 编辑 / 删除 / 重排。
 *  已激活 / 已停用：只读。 */
export function RouteFlow(props: {
  row: MesRow
  readOnly?: boolean
  /** 需高亮的工步 id（如批次的当前工步） */
  highlight?: string | null
}) {
  return (
    <ReactFlowProvider>
      <RouteFlowInner {...props} />
    </ReactFlowProvider>
  )
}

function RouteFlowInner({
  row,
  readOnly = false,
  highlight = null,
}: {
  row: MesRow
  readOnly?: boolean
  highlight?: string | null
}) {
  const qc = useQueryClient()
  const tk = useTenantKey()
  const { entity: stepEntity } = useMesEntity('route_step')
  const { entity: routeEntity } = useMesEntity('route')
  const editable =
    !readOnly && row.status === 'draft' && !!routeEntity?.can_write
  const { query: steps, queryKey: stepsKey } = useRouteSteps(row.id)
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
  const { screenToFlowPosition, getNodes, fitView } = useReactFlow()
  const measured = useNodesInitialized()
  const fitted = useRef(false)
  const [dropEdge, setDropEdge] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [editing, setEditing] = useState<MesRow | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<MesRow | null>(null)
  const [branch, setBranch] = useState<Branch | null>(null)

  const refresh = useCallback(
    () => qc.invalidateQueries({ queryKey: ['mes', 'route_step'] }),
    [qc]
  )
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
  /** 保存节点位置（可选：随后重排工步）；位置先写入缓存，避免等待刷新时节点跳回。 */
  const commit = useMutation({
    mutationFn: async ({
      layout,
      order,
    }: {
      layout: Record<string, StepLayout | null>
      order?: string[]
    }) => {
      await saveRouteLayout(row.id, layout)
      if (order) await reorderRouteSteps(row.id, order)
    },
    onMutate: ({ layout }) =>
      qc.setQueryData<typeof steps.data>(stepsKey, (old) =>
        old
          ? {
              ...old,
              data: old.data.map((s) =>
                s.id in layout ? { ...s, layout: layout[s.id] } : s
              ),
            }
          : old
      ),
    onSuccess: refresh,
    onError: (e) => {
      onErr(e)
      refresh()
    },
  })
  /** 从面板拖入新工步：创建、保存全部节点位置，必要时插入到指定位置。 */
  const add = useMutation({
    mutationFn: async ({
      item,
      at,
      index,
    }: {
      item: PaletteItem
      at: { x: number; y: number }
      index: number | null
    }) => {
      const last = (list[list.length - 1]?.seq as number | undefined) ?? 0
      const created = await mesApi.create('route_step', {
        route_id: row.id,
        seq: last + 10,
        step_type: item.kind,
        ...(item.kind === 'operation'
          ? { operation_id: item.id }
          : { sub_route_id: item.id }),
      })
      const pos = new Map(getNodes().map((n) => [n.id, n.position]))
      await saveRouteLayout(row.id, {
        ...layoutOf(list, (id) => pos.get(id)),
        [created.id]: at,
      })
      if (index !== null && index < list.length) {
        const ids = list.map((s) => s.id)
        await reorderRouteSteps(row.id, [
          ...ids.slice(0, index),
          created.id,
          ...ids.slice(index),
        ])
      }
    },
    onSuccess: refresh,
    onError: (e) => {
      onErr(e)
      refresh()
    },
  })

  const built = useMemo(() => {
    const linked = new Set(list.map((s) => String(s.rework_route_id ?? '')))
    return buildGraph({
      list,
      subs: subs.data,
      options: editable
        ? (reworks.data?.data ?? []).filter((r) => !linked.has(r.id))
        : [],
      highlight,
    })
  }, [list, subs.data, reworks.data, editable, highlight])
  // 节点首次完成测量后适配视图（之后不再自动改动用户的视角）
  useEffect(() => {
    if (measured && !fitted.current) {
      fitted.current = true
      fitView({ padding: 0.15 })
    }
  }, [measured, fitView])
  // 数据变化后重建节点（保留选中状态）；节点位置在拖动过程中由本地状态持有
  const [nodes, setNodes] = useState<Node[]>(built.nodes)
  const [seen, setSeen] = useState(built)
  if (seen !== built) {
    setSeen(built)
    const sel = new Set(nodes.filter((n) => n.selected).map((n) => n.id))
    setNodes(built.nodes.map((n) => ({ ...n, selected: sel.has(n.id) })))
  }
  const edges = useMemo(
    () =>
      built.edges.map((e): Edge => {
        const k = String(e.data?.kind)
        const editableKind = editable && (k === 'branch' || k === 'rework')
        return {
          ...e,
          labelBgStyle: { fill: 'var(--background)', fillOpacity: 0.95 },
          labelBgPadding: [6, 3] as [number, number],
          labelBgBorderRadius: 4,
          deletable: editableKind,
          reconnectable: editableKind ? 'target' : false,
          ...(e.id === dropEdge
            ? {
                animated: true,
                style: { ...e.style, stroke: 'var(--primary)', strokeWidth: 4 },
              }
            : {}),
        }
      }),
    [built.edges, dropEdge, editable]
  )

  /** 当前主链上各工步节点的位置（按序号）与起止节点位置。 */
  const chain = useCallback(() => {
    const all = getNodes()
    const at = new Map(all.map((n) => [n.id, n.position]))
    return {
      ordered: list.flatMap((s) => {
        const p = at.get(stepNodeId(s.id))
        return p ? [{ id: s.id, x: p.x, y: p.y }] : []
      }),
      start: at.get('start') ?? { x: 0, y: 0 },
      end: at.get('end') ?? { x: 0, y: 0 },
    }
  }, [getNodes, list])
  /** 点 `p` 命中的主链插入位置（同时更新高亮连线）。 */
  const probe = (p: { x: number; y: number }, skip?: string) => {
    const c = chain()
    const idx = insertIndexAt(p, c.ordered, c.start, c.end, skip)
    const ids = c.ordered.filter((s) => s.id !== skip).map((s) => s.id)
    // 放回原位等同没有变化
    const same =
      skip &&
      idx !== null &&
      list.map((s) => s.id).join() ===
        [...ids.slice(0, idx), skip, ...ids.slice(idx)].join()
    const hit = same ? null : idx
    setDropEdge(hit === null ? null : mainEdgeId(ids.map(stepNodeId), hit))
    return hit
  }

  const onNodesChange = (ch: NodeChange[]) =>
    setNodes((ns) => applyNodeChanges(ch, ns))
  const onNodeDrag = (_: unknown, n: Node) => {
    if (n.type === 'step')
      probe(
        { x: n.position.x + W / 2, y: n.position.y + H / 2 },
        stepIdOf(n.id)!
      )
  }
  const onNodeDragStop = (_: unknown, dragged: Node) => {
    // 以松手时的位置重新判断落点，不依赖拖动中的状态
    const index =
      dragged.type === 'step'
        ? probe(
            { x: dragged.position.x + W / 2, y: dragged.position.y + H / 2 },
            stepIdOf(dragged.id)!
          )
        : null
    setDropEdge(null)
    const pos = new Map(getNodes().map((n) => [n.id, n.position]))
    pos.set(dragged.id, dragged.position)
    const layout = layoutOf(list, (id) => pos.get(id))
    let order: string[] | undefined
    if (dragged.type === 'step' && index !== null) {
      const id = stepIdOf(dragged.id)!
      const ids = list.map((s) => s.id).filter((x) => x !== id)
      order = [...ids.slice(0, index), id, ...ids.slice(index)]
    }
    commit.mutate({ layout, order })
  }
  const onDragOver = (e: DragEvent) => {
    if (!editable || !e.dataTransfer.types.includes(PALETTE_MIME)) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
    probe(screenToFlowPosition({ x: e.clientX, y: e.clientY }))
  }
  const onDrop = (e: DragEvent) => {
    const raw = e.dataTransfer.getData(PALETTE_MIME)
    if (!editable || !raw) return
    e.preventDefault()
    const p = screenToFlowPosition({ x: e.clientX, y: e.clientY })
    const index = probe(p)
    setDropEdge(null)
    add.mutate({
      item: JSON.parse(raw) as PaletteItem,
      at: { x: snap(p.x - W / 2), y: snap(p.y - H / 2) },
      index,
    })
  }

  const stepOf = (nodeId: string) => {
    const id = nodeId.startsWith('s-') ? stepIdOf(nodeId) : null
    return list.find((s) => s.id === id)
  }
  /** 把返工路线节点 `opt-…` 的位置记为该工步返工节点的位置。 */
  const connectRework = (from: MesRow, target: string) => {
    const routeId = target.slice('opt-'.length)
    const at = getNodes().find((n) => n.id === target)?.position
    patch.mutate(
      { id: from.id, body: { rework_route_id: routeId } },
      {
        onSuccess: () => {
          if (!at) return
          const pos = new Map(getNodes().map((n) => [n.id, n.position]))
          const layout = layoutOf(list, (id) => pos.get(id))
          const own = layout[from.id]
          if (own)
            commit.mutate({
              layout: { [from.id]: { ...own, rx: at.x, ry: at.y } },
            })
        },
      }
    )
  }
  const onConnect = (c: Connection) => {
    const from = stepOf(c.source)
    if (!from || !editable) return
    if (c.target.startsWith('opt-')) return connectRework(from, c.target)
    const to = stepOf(c.target)
    if (to && to.id !== from.id)
      setBranch({ from, to, cond: String(from.branch_condition ?? '') })
  }
  const onReconnect = (old: Edge, c: Connection) => {
    const s = old.data?.step as MesRow | undefined
    if (!s || !editable) return
    if (old.data?.kind === 'branch') {
      const to = stepOf(c.target)
      if (to && to.id !== s.id)
        patch.mutate({ id: s.id, body: { branch_to_seq: to.seq } })
    } else if (old.data?.kind === 'rework' && c.target.startsWith('opt-'))
      connectRework(s, c.target)
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
  /** Delete 键：工步节点先弹确认框，连线直接删除。 */
  const onBeforeDelete = async ({
    nodes: ns,
    edges: es,
  }: {
    nodes: Node[]
    edges: Edge[]
  }) => {
    const target = ns.find((n) => n.type === 'step')
    if (target) setDeleting(stepOf(target.id) ?? null)
    return target || es.length === 0 ? false : { nodes: [], edges: es }
  }
  const autoLayout = () =>
    commit.mutate(
      {
        layout: Object.fromEntries(list.map((s) => [s.id, null])),
      },
      { onSuccess: () => toast.success(t('mes.flow.autoLayoutDone')) }
    )

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
      <div className='flex h-[68vh] overflow-hidden rounded-md border'>
        {editable && <Palette />}
        <div
          className='relative min-w-0 flex-1'
          onDragOver={onDragOver}
          onDragLeave={() => setDropEdge(null)}
          onDrop={onDrop}
        >
          {steps.isLoading ? (
            <Loader2 className='m-auto mt-20 animate-spin' />
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              nodesDraggable={editable}
              nodesConnectable={editable}
              snapToGrid={editable}
              snapGrid={[GRID, GRID]}
              onNodesChange={onNodesChange}
              onNodeDrag={onNodeDrag}
              onNodeDragStop={onNodeDragStop}
              onConnect={onConnect}
              onReconnect={onReconnect}
              onEdgesDelete={onEdgesDelete}
              onBeforeDelete={onBeforeDelete}
              deleteKeyCode={editable ? ['Backspace', 'Delete'] : null}
              onNodeClick={(_, n) =>
                setSelected(n.id.startsWith('s-') ? stepIdOf(n.id) : null)
              }
              onNodeDoubleClick={(_, n) => {
                const s = stepOf(n.id)
                if (editable && s) setEditing(s)
              }}
              onEdgeDoubleClick={(_, e) => {
                const s = e.data?.step as MesRow | undefined
                const to = list.find(
                  (x) => Number(x.seq) === Number(s?.branch_to_seq)
                )
                if (editable && e.data?.kind === 'branch' && s && to)
                  setBranch({
                    from: s,
                    to,
                    cond: String(s.branch_condition ?? ''),
                  })
              }}
              onPaneClick={() => setSelected(null)}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={GRID} />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable className='!bg-background' />
              {editable && list.length > 0 && (
                <Panel position='top-left'>
                  <Button
                    size='sm'
                    variant='outline'
                    className='bg-background'
                    onClick={autoLayout}
                    disabled={commit.isPending}
                  >
                    <LayoutTemplate />
                    {t('mes.flow.autoLayout')}
                  </Button>
                </Panel>
              )}
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
                <IconButton
                  label={t('common.close')}
                  variant='ghost'
                  className='size-7'
                  onClick={() => setSelected(null)}
                >
                  <X className='size-4' />
                </IconButton>
              </div>
              <dl className='space-y-1 text-xs'>
                {(['operation', 'sub_route', 'rework_route'] as const).map(
                  (k) =>
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
                      {String(sel.branch_condition)} →{' '}
                      {String(sel.branch_to_seq)}
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
                  <IconButton
                    label={t('mes.moveUp')}
                    variant='outline'
                    disabled={idx <= 0}
                    onClick={() => swap(idx, idx - 1)}
                  >
                    <ArrowUp />
                  </IconButton>
                  <IconButton
                    label={t('mes.moveDown')}
                    variant='outline'
                    disabled={idx >= list.length - 1}
                    onClick={() => swap(idx, idx + 1)}
                  >
                    <ArrowDown />
                  </IconButton>
                  <IconButton
                    label={t('common.delete')}
                    variant='outline'
                    onClick={() => setDeleting(sel)}
                  >
                    <Trash2 className='text-destructive' />
                  </IconButton>
                </div>
              )}
            </aside>
          )}
        </div>
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
