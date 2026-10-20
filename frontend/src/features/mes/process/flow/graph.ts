/** 路线流程图的图结构：节点 / 连线生成、自动布局、已存位置、拖到连线上插入的命中判断。 */
import { t } from '@/i18n'
import dagre from '@dagrejs/dagre'
import { MarkerType, type Edge, type Node } from '@xyflow/react'
import type { MesRow } from '@/lib/api/mes/common'
import type { StepLayout } from '@/lib/api/mes/process'

/** 工步 / 引用节点宽度、工步节点高度、起止节点尺寸、吸附网格。 */
export const W = 260
export const H = 72
export const TERM_W = 100
export const TERM_H = 32
export const GRID = 16
/** 引用节点（子路线 / 返工）与所属工步的水平间距、纵向间距。 */
const REF_DX = 110
const REF_GAP = 24
/** 箭头大小与各类连线的颜色。 */
const ARROW = 22
const MAIN = '#64748b'
const CALL = '#6366f1'
const REWORK = '#dc2626'
const BRANCH = '#d97706'
/** 拖动节点到连线上插入 / 重排的命中距离（流程图坐标）。 */
const HIT = 36

export type StepData = { step: MesRow; current: boolean }
export type RefData = {
  label: string
  kind: 'sub' | 'rework'
  steps?: MesRow[]
  /** 是否已被工步关联（未关联的返工路线仅作为连线目标） */
  linked: boolean
}
export type TermData = { label: string }

export const stepNodeId = (stepId: string) => `s-${stepId}`
const subNodeId = (stepId: string) => `sub-${stepId}`
const reworkNodeId = (stepId: string) => `rw-${stepId}`
const optionNodeId = (routeId: string) => `opt-${routeId}`

/** 节点 id 对应的工步 id（工步节点 `s-`、子路线节点 `sub-`、返工节点 `rw-`）。 */
export function stepIdOf(nodeId: string): string | null {
  for (const p of ['s-', 'sub-', 'rw-'])
    if (nodeId.startsWith(p)) return nodeId.slice(p.length)
  return null
}

const refHeight = (n: number) => H + 16 * n

/** 已存的节点位置（`layout` 列）；格式不对时视为未保存。 */
function savedLayout(step: MesRow): StepLayout | null {
  const l = step.layout as Partial<StepLayout> | null | undefined
  return l && Number.isFinite(l.x) && Number.isFinite(l.y)
    ? (l as StepLayout)
    : null
}

type Dims = { id: string; w: number; h: number }

/** 主链与子路线 / 返工调用参与自动布局（dagre，自上而下）。 */
function autoLayout(
  nodes: Dims[],
  links: [string, string][]
): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 50 })
  g.setDefaultEdgeLabel(() => ({}))
  for (const n of nodes) g.setNode(n.id, { width: n.w, height: n.h })
  for (const [a, b] of links) g.setEdge(a, b)
  dagre.layout(g)
  return new Map(
    nodes.map((n) => {
      const p = g.node(n.id)
      return [n.id, { x: p.x - n.w / 2, y: p.y - n.h / 2 }]
    })
  )
}

interface GraphInput {
  /** 按序号排列的工步 */
  list: MesRow[]
  /** 子路线 id -> 其工步（节点内展示） */
  subs?: Record<string, MesRow[]>
  /** 未被任何工步关联、可作为返工连线目标的返工路线（仅编辑时给出） */
  options?: MesRow[]
  /** 需高亮的工步 id */
  highlight?: string | null
  /** 忽略已存位置，全部自动布局 */
  ignoreSaved?: boolean
}

/**
 * 生成节点与连线。工步及其子路线 / 返工节点优先用已存位置，其余由 dagre 自动布局；
 * 起止节点跟随首 / 末工步，返工路线选项排在右侧。
 */
export function buildGraph({
  list,
  subs = {},
  options = [],
  highlight = null,
  ignoreSaved = false,
}: GraphInput): { nodes: Node[]; edges: Edge[] } {
  const arrow = (color: string) => ({
    type: MarkerType.ArrowClosed,
    width: ARROW,
    height: ARROW,
    color,
  })
  const bySeq = new Map(list.map((s) => [Number(s.seq), s]))
  const dims: Dims[] = []
  const links: [string, string][] = []
  const nodes: Node[] = []
  const edges: Edge[] = []
  const step = new Map<string, MesRow>()
  const rows = new Map<string, { subH: number; rwH: number }>()
  let branchCount = 0

  let prev: string | null = null
  for (const s of list) {
    const id = stepNodeId(s.id)
    step.set(id, s)
    const subRows =
      s.step_type === 'sub_route' && s.sub_route_id
        ? (subs[String(s.sub_route_id)] ?? [])
        : null
    const subH = subRows ? refHeight(subRows.length) : 0
    const rwH = s.rework_route_id ? H : 0
    rows.set(id, { subH, rwH })
    dims.push({
      id,
      w: W,
      h: Math.max(H, subH + (subH && rwH ? REF_GAP : 0) + rwH),
    })
    nodes.push({
      id,
      type: 'step',
      position: { x: 0, y: 0 },
      data: { step: s, current: highlight === s.id } satisfies StepData,
    })
    if (prev) {
      edges.push({
        id: `m-${prev}-${id}`,
        source: prev,
        target: id,
        markerEnd: arrow(MAIN),
        style: { stroke: MAIN, strokeWidth: 1.5 },
        data: { kind: 'main' },
      })
      links.push([prev, id])
    }
    prev = id
    if (subRows) {
      const sid = subNodeId(s.id)
      step.set(sid, s)
      nodes.push({
        id: sid,
        type: 'ref',
        position: { x: 0, y: 0 },
        data: {
          label: String(s.sub_route_label),
          kind: 'sub',
          steps: subRows,
          linked: true,
        } satisfies RefData,
      })
      // 调用与返回合成一条双向箭头，避免回路线穿过其他节点
      edges.push({
        id: `call-${s.id}`,
        source: id,
        sourceHandle: 'side',
        target: sid,
        label: `${t('mes.edgeCall')} / ${t('mes.edgeReturn')}`,
        animated: true,
        markerStart: arrow(CALL),
        markerEnd: arrow(CALL),
        style: { stroke: CALL, strokeWidth: 1.5, strokeDasharray: '6 4' },
        data: { kind: 'call' },
      })
    }
    if (s.rework_route_id) {
      const rid = reworkNodeId(s.id)
      step.set(rid, s)
      nodes.push({
        id: rid,
        type: 'ref',
        position: { x: 0, y: 0 },
        data: {
          label: String(s.rework_route_label),
          kind: 'rework',
          linked: true,
        } satisfies RefData,
      })
      edges.push({
        id: `rw-${s.id}`,
        source: id,
        sourceHandle: 'side',
        target: rid,
        label: t('mes.edgeRework'),
        markerEnd: arrow(REWORK),
        style: { stroke: REWORK, strokeWidth: 1.5, strokeDasharray: '4 3' },
        data: { kind: 'rework', step: s },
      })
    }
    const to =
      s.branch_to_seq != null ? bySeq.get(Number(s.branch_to_seq)) : null
    if (to)
      edges.push({
        id: `br-${s.id}`,
        source: id,
        sourceHandle: 'left-out',
        target: stepNodeId(to.id),
        targetHandle: 'left-in',
        label: String(s.branch_condition ?? ''),
        labelStyle: { fill: BRANCH, fontWeight: 600 },
        markerEnd: arrow(BRANCH),
        style: { stroke: BRANCH, strokeWidth: 2 },
        type: 'smoothstep',
        // 两端都在左侧（右侧留给子路线 / 返工），绕到节点外侧；错开偏移避免多条分支重叠
        pathOptions: { offset: 36 + 14 * branchCount++, borderRadius: 14 },
        data: { kind: 'branch', step: s },
      } as Edge)
  }

  // 位置：已存的优先；其余主链自动布局，子路线 / 返工节点排在所属工步右侧
  const auto = autoLayout(dims, links)
  const place = new Map<string, { x: number; y: number }>()
  const saved = (id: string, s: MesRow) => {
    const l = ignoreSaved ? null : savedLayout(s)
    const k = id.startsWith('sub-') ? 'a' : id.startsWith('rw-') ? 'r' : ''
    const x = l && (k ? l[`${k}x`] : l.x)
    const y = l && (k ? l[`${k}y`] : l.y)
    return x != null && y != null ? { x, y } : null
  }
  for (const [id, s] of step) {
    if (!id.startsWith('s-')) continue
    place.set(id, saved(id, s) ?? auto.get(id)!)
    const p = place.get(id)!
    const r = rows.get(id)!
    const x = p.x + W + REF_DX
    if (r.subH)
      place.set(subNodeId(s.id), saved(subNodeId(s.id), s) ?? { x, y: p.y })
    if (r.rwH)
      place.set(
        reworkNodeId(s.id),
        saved(reworkNodeId(s.id), s) ?? {
          x,
          y: p.y + (r.subH ? r.subH + REF_GAP : 0),
        }
      )
  }
  for (const n of nodes) n.position = place.get(n.id)!

  // 起止节点：首工步之上、末工步之下
  const first = list[0]
  const last = list[list.length - 1]
  const at = (s: MesRow | undefined, above: boolean) => {
    const p = s ? place.get(stepNodeId(s.id)) : null
    return {
      x: (p?.x ?? 0) + (W - TERM_W) / 2,
      y: p ? (above ? p.y - 80 : p.y + H + 50) : above ? 0 : 120,
    }
  }
  nodes.push(
    {
      id: 'start',
      type: 'term',
      position: at(first, true),
      data: { label: t('mes.flowStart') } satisfies TermData,
      draggable: false,
      selectable: false,
      deletable: false,
    },
    {
      id: 'end',
      type: 'term',
      position: at(last, false),
      data: { label: t('mes.flowEnd') } satisfies TermData,
      draggable: false,
      selectable: false,
      deletable: false,
    }
  )
  edges.push(
    {
      id: first ? `m-start-${stepNodeId(first.id)}` : 'm-start-end',
      source: 'start',
      target: first ? stepNodeId(first.id) : 'end',
      markerEnd: arrow(MAIN),
      style: { stroke: MAIN, strokeWidth: 1.5 },
      data: { kind: 'main' },
    },
    ...(last
      ? [
          {
            id: `m-${stepNodeId(last.id)}-end`,
            source: stepNodeId(last.id),
            target: 'end',
            markerEnd: arrow(MAIN),
            style: { stroke: MAIN, strokeWidth: 1.5 },
            data: { kind: 'main' },
          } satisfies Edge,
        ]
      : [])
  )

  // 未关联的返工路线：排在右侧，只作为连线目标
  const right = Math.max(0, ...nodes.map((n) => n.position.x)) + W + 120
  const top = Math.min(0, ...nodes.map((n) => n.position.y))
  options.forEach((r, i) =>
    nodes.push({
      id: optionNodeId(r.id),
      type: 'ref',
      position: { x: right, y: top + i * (H + 24) },
      data: {
        label: `${r.code} v${r.version}`,
        kind: 'rework',
        linked: false,
      } satisfies RefData,
      draggable: false,
      deletable: false,
    })
  )
  return { nodes, edges }
}

/** 由当前节点位置得到各工步的存储坐标（含其子路线 `ax / ay`、返工节点 `rx / ry`）。 */
export function layoutOf(
  list: MesRow[],
  pos: (nodeId: string) => { x: number; y: number } | undefined
): Record<string, StepLayout> {
  const out: Record<string, StepLayout> = {}
  for (const s of list) {
    const p = pos(stepNodeId(s.id))
    if (!p) continue
    const sub = pos(subNodeId(s.id))
    const rw = pos(reworkNodeId(s.id))
    out[s.id] = {
      x: p.x,
      y: p.y,
      ...(sub ? { ax: sub.x, ay: sub.y } : {}),
      ...(rw ? { rx: rw.x, ry: rw.y } : {}),
    }
  }
  return out
}

function segDistance(
  p: { x: number; y: number },
  a: { x: number; y: number },
  b: { x: number; y: number }
): number {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const len2 = dx * dx + dy * dy
  const u = len2
    ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2))
    : 0
  return Math.hypot(p.x - (a.x + u * dx), p.y - (a.y + u * dy))
}

/**
 * 点 `p` 落在主链哪两个相邻工步之间的连线上（距离小于 {@link HIT}）。
 *
 * @param p - 流程图坐标（通常为被拖动节点的中心）
 * @param ordered - 按序号排列的工步节点左上角位置
 * @param start - 起点节点左上角位置
 * @param end - 终点节点左上角位置
 * @param skip - 被拖动的工步 id（命中判断时从主链中去掉）
 * @returns 插入下标（在去掉 `skip` 的工步序列中的位置），未命中为 null
 */
export function insertIndexAt(
  p: { x: number; y: number },
  ordered: { id: string; x: number; y: number }[],
  start: { x: number; y: number },
  end: { x: number; y: number },
  skip?: string
): number | null {
  const items = ordered.filter((s) => s.id !== skip)
  const bottom = (x: number, y: number, w: number, h: number) => ({
    x: x + w / 2,
    y: y + h,
  })
  const top = (x: number, y: number, w: number) => ({ x: x + w / 2, y })
  const out = [
    bottom(start.x, start.y, TERM_W, TERM_H),
    ...items.map((s) => bottom(s.x, s.y, W, H)),
  ]
  const into = [
    ...items.map((s) => top(s.x, s.y, W)),
    top(end.x, end.y, TERM_W),
  ]
  let best: number | null = null
  let bestD = HIT
  for (let i = 0; i < out.length; i++) {
    const d = segDistance(p, out[i], into[i])
    if (d < bestD) {
      bestD = d
      best = i
    }
  }
  return best
}

/** 主链连线 id（与 {@link buildGraph} 一致）：插入下标 `i` 对应的相邻两端之间。 */
export function mainEdgeId(stepNodeIds: string[], i: number): string {
  const a = i === 0 ? 'start' : stepNodeIds[i - 1]
  const b = i === stepNodeIds.length ? 'end' : stepNodeIds[i]
  return `m-${a}-${b}`
}
