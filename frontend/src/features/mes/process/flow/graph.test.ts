import { describe, expect, it } from 'vitest'
import type { MesRow } from '@/lib/api/mes/common'
import {
  buildGraph,
  H,
  insertIndexAt,
  layoutOf,
  mainEdgeId,
  stepIdOf,
  stepNodeId,
  TERM_H,
  TERM_W,
  W,
} from './graph'

const step = (
  id: string,
  seq: number,
  extra: Partial<MesRow> = {}
): MesRow => ({
  id,
  seq,
  step_type: 'operation',
  operation_label: `OP${seq}`,
  ...extra,
})
const pos = (g: ReturnType<typeof buildGraph>, id: string) =>
  g.nodes.find((n) => n.id === id)!.position

describe('buildGraph', () => {
  const list = [step('a', 10), step('b', 20), step('c', 30)]

  it('主链：起点 → 各工步 → 终点，按序号连线', () => {
    const g = buildGraph({ list })
    const main = g.edges.filter((e) => e.data?.kind === 'main')
    expect(main.map((e) => e.id).sort()).toEqual([
      'm-s-a-s-b',
      'm-s-b-s-c',
      'm-s-c-end',
      'm-start-s-a',
    ])
  })

  it('已存位置优先；未存位置自动布局且互不重叠', () => {
    const g = buildGraph({
      list: [step('a', 10, { layout: { x: 500, y: 40 } }), ...list.slice(1)],
    })
    expect(pos(g, 's-a')).toEqual({ x: 500, y: 40 })
    expect(pos(g, 's-b').y).toBeGreaterThanOrEqual(0)
    expect(pos(g, 's-b')).not.toEqual(pos(g, 's-c'))
  })

  it('子路线与返工节点各有独立位置', () => {
    const s = step('a', 10, {
      step_type: 'sub_route',
      sub_route_id: 'r1',
      sub_route_label: 'SUB',
      rework_route_id: 'r2',
      rework_route_label: 'RW',
      layout: { x: 0, y: 0, ax: 400, ay: 10, rx: 420, ry: 200 },
    })
    const g = buildGraph({ list: [s] })
    expect(pos(g, 'sub-a')).toEqual({ x: 400, y: 10 })
    expect(pos(g, 'rw-a')).toEqual({ x: 420, y: 200 })
  })

  it('起止节点跟随首 / 末工步', () => {
    const g = buildGraph({
      list: [
        step('a', 10, { layout: { x: 100, y: 200 } }),
        step('b', 20, { layout: { x: 100, y: 600 } }),
      ],
    })
    expect(pos(g, 'start').x).toBe(100 + (W - TERM_W) / 2)
    expect(pos(g, 'start').y).toBeLessThan(200)
    expect(pos(g, 'end').y).toBeGreaterThan(600 + H)
  })

  it('ignoreSaved 忽略已存位置；格式不对的位置视为未保存', () => {
    const bad = step('a', 10, { layout: { x: 'x' } as never })
    expect(pos(buildGraph({ list: [bad] }), 's-a')).toBeDefined()
    const saved = [step('a', 10, { layout: { x: 999, y: 999 } })]
    expect(
      pos(buildGraph({ list: saved, ignoreSaved: true }), 's-a').x
    ).not.toBe(999)
  })

  it('未关联的返工路线作为连线目标排在右侧，且不可拖动', () => {
    const g = buildGraph({
      list,
      options: [{ id: 'r9', code: 'RW', version: 1 } as MesRow],
    })
    const opt = g.nodes.find((n) => n.id === 'opt-r9')!
    expect(opt.draggable).toBe(false)
    expect(opt.position.x).toBeGreaterThan(pos(g, 's-a').x + W)
  })

  it('分支连线指向目标序号的工步', () => {
    const g = buildGraph({
      list: [
        step('a', 10),
        step('b', 20, { branch_condition: 'x', branch_to_seq: 10 }),
      ],
    })
    const br = g.edges.find((e) => e.id === 'br-b')!
    expect([br.source, br.target]).toEqual(['s-b', 's-a'])
  })
})

describe('layoutOf / stepIdOf', () => {
  it('收集工步及其引用节点的位置', () => {
    const list = [step('a', 10), step('b', 20)]
    const at: Record<string, { x: number; y: number }> = {
      's-a': { x: 1, y: 2 },
      'rw-a': { x: 3, y: 4 },
      's-b': { x: 5, y: 6 },
    }
    expect(layoutOf(list, (id) => at[id])).toEqual({
      a: { x: 1, y: 2, rx: 3, ry: 4 },
      b: { x: 5, y: 6 },
    })
  })

  it('节点 id 还原工步 id', () => {
    expect(stepIdOf('s-x1')).toBe('x1')
    expect(stepIdOf('sub-x1')).toBe('x1')
    expect(stepIdOf('rw-x1')).toBe('x1')
    expect(stepIdOf('start')).toBeNull()
    expect(stepNodeId('x1')).toBe('s-x1')
  })
})

describe('insertIndexAt：拖到连线上插入', () => {
  // 三个工步竖直排列，间隔 200
  const ordered = [
    { id: 'a', x: 0, y: 100 },
    { id: 'b', x: 0, y: 300 },
    { id: 'c', x: 0, y: 500 },
  ]
  const start = { x: (W - TERM_W) / 2, y: 20 }
  const end = { x: (W - TERM_W) / 2, y: 700 }
  const mid = (i: number) => ({ x: W / 2, y: ordered[i].y + H + (200 - H) / 2 })

  it('落在 a-b 之间的连线上 → 插入下标 1', () => {
    expect(insertIndexAt(mid(0), ordered, start, end)).toBe(1)
  })

  it('落在起点与首工步之间 → 0；末工步与终点之间 → 末尾', () => {
    expect(
      insertIndexAt({ x: W / 2, y: 20 + TERM_H + 20 }, ordered, start, end)
    ).toBe(0)
    expect(insertIndexAt({ x: W / 2, y: 620 }, ordered, start, end)).toBe(3)
  })

  it('远离所有连线不命中', () => {
    expect(insertIndexAt({ x: 900, y: 300 }, ordered, start, end)).toBeNull()
  })

  it('skip 把被拖动的工步从主链上去掉', () => {
    // 拖动 b：a、c 之间成为一段，落在其中点 → 下标 1（等于原位置）
    expect(insertIndexAt({ x: W / 2, y: 330 }, ordered, start, end, 'b')).toBe(
      1
    )
  })

  it('连线 id 与 buildGraph 一致', () => {
    const ids = ['s-a', 's-b', 's-c']
    expect(mainEdgeId(ids, 0)).toBe('m-start-s-a')
    expect(mainEdgeId(ids, 1)).toBe('m-s-a-s-b')
    expect(mainEdgeId(ids, 3)).toBe('m-s-c-end')
  })
})
