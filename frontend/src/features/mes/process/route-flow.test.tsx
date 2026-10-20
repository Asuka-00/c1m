import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/styles/index.css'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { RouteFlow } from './route-flow'

const process = vi.hoisted(() => ({
  saveRouteLayout: vi.fn().mockResolvedValue({ saved: 1 }),
  reorderRouteSteps: vi.fn().mockResolvedValue({ data: [] }),
}))
vi.mock('@/lib/api/mes/process', async (orig) => ({
  ...(await orig<typeof import('@/lib/api/mes/process')>()),
  ...process,
}))

const step = (id: string, seq: number, y: number): MesRow => ({
  id,
  seq,
  step_type: 'operation',
  operation_label: `OP${seq}`,
  layout: { x: 100, y },
})
const STEPS = [step('a', 10, 100), step('b', 20, 300), step('c', 30, 500)]

const entity = (code: string) => ({
  code,
  fields: [],
  can_write: true,
  can_read: true,
})

async function show(status = 'draft') {
  vi.spyOn(mesApi, 'list').mockImplementation(async (code) => {
    const data =
      code === 'route_step'
        ? STEPS
        : code === 'operation'
          ? [{ id: 'OP1', code: 'COAT', name: 'Coat' }]
          : []
    return { data, count: data.length } as never
  })
  vi.spyOn(mesApi, 'create').mockResolvedValue({ id: 'n', seq: 40 } as never)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [entity('route_step'), entity('route')],
    enums: {},
    perms: [],
  })
  const s = await render(
    <QueryClientProvider client={qc}>
      <RouteFlow row={{ id: 'R1', status, code: 'R', version: 1 }} />
    </QueryClientProvider>
  )
  await vi.waitFor(() =>
    expect(s.container.querySelector('[data-testid=step-30]')).not.toBeNull()
  )
  // 等 fitView 完成（视口变换稳定）
  await new Promise((r) => setTimeout(r, 400))
  return s
}

const rect = (el: Element) => el.getBoundingClientRect()
const center = (el: Element) => {
  const r = rect(el)
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
}
const node = (container: Element, seq: number) =>
  container
    .querySelector(`[data-testid=step-${seq}]`)!
    .closest('.react-flow__node')!

/** 用鼠标事件拖动节点（React Flow 基于 d3-drag：mousedown 在节点上，其余在 window 上）。 */
async function drag(el: Element, to: { x: number; y: number }) {
  const from = center(el)
  const ev = (type: string, p: { x: number; y: number }) =>
    new MouseEvent(type, {
      bubbles: true,
      cancelable: true,
      clientX: p.x,
      clientY: p.y,
      button: 0,
      view: window,
    })
  el.dispatchEvent(ev('mousedown', from))
  for (let i = 1; i <= 8; i++) {
    const p = {
      x: from.x + ((to.x - from.x) * i) / 8,
      y: from.y + ((to.y - from.y) * i) / 8,
    }
    window.dispatchEvent(ev('mousemove', p))
    await new Promise((r) => setTimeout(r, 20))
  }
  window.dispatchEvent(ev('mouseup', to))
}

afterEach(() => {
  vi.restoreAllMocks()
  process.saveRouteLayout.mockClear()
  process.reorderRouteSteps.mockClear()
})

describe('RouteFlow 拖拽编辑', () => {
  it('拖动节点后保存新位置（不改变顺序）', async () => {
    const s = await show()
    const el = node(s.container, 20)
    const c = center(el)
    await drag(el, { x: c.x + 120, y: c.y })
    await vi.waitFor(() => expect(process.saveRouteLayout).toHaveBeenCalled())
    const [routeId, layout] = process.saveRouteLayout.mock.calls[0]
    expect(routeId).toBe('R1')
    expect(layout.b.x).toBeGreaterThan(100)
    expect(layout.a).toEqual({ x: 100, y: 100 })
    expect(process.reorderRouteSteps).not.toHaveBeenCalled()
  })

  it('把第 3 步拖到第 1、2 步之间的连线上 → 重排为 a, c, b', async () => {
    const s = await show()
    const a = rect(node(s.container, 10))
    const b = rect(node(s.container, 20))
    const target = {
      x: a.x + a.width / 2,
      y: (a.bottom + b.top) / 2,
    }
    await drag(node(s.container, 30), target)
    await vi.waitFor(() =>
      expect(process.reorderRouteSteps).toHaveBeenCalledWith('R1', [
        'a',
        'c',
        'b',
      ])
    )
    expect(process.saveRouteLayout).toHaveBeenCalled()
  })

  it('从面板拖入工序 → 创建工步、保存位置并插入到连线上', async () => {
    const s = await show()
    const item = await vi.waitFor(() => {
      const el = s.container.querySelector(
        '[data-testid=palette-operation-OP1]'
      )
      expect(el).not.toBeNull()
      return el!
    })
    const a = rect(node(s.container, 10))
    const b = rect(node(s.container, 20))
    const at = { x: a.x + a.width / 2, y: (a.bottom + b.top) / 2 }
    const canvas = s.container.querySelector('.react-flow')!.parentElement!
    const dt = new DataTransfer()
    item.dispatchEvent(
      new DragEvent('dragstart', { bubbles: true, dataTransfer: dt })
    )
    const over = (type: string) =>
      canvas.dispatchEvent(
        new DragEvent(type, {
          bubbles: true,
          cancelable: true,
          dataTransfer: dt,
          clientX: at.x,
          clientY: at.y,
        })
      )
    over('dragover')
    over('drop')
    await vi.waitFor(() =>
      expect(mesApi.create).toHaveBeenCalledWith(
        'route_step',
        expect.objectContaining({
          route_id: 'R1',
          seq: 40,
          step_type: 'operation',
          operation_id: 'OP1',
        })
      )
    )
    await vi.waitFor(() =>
      expect(process.reorderRouteSteps).toHaveBeenCalledWith('R1', [
        'a',
        'n',
        'b',
        'c',
      ])
    )
    const layout = process.saveRouteLayout.mock.calls[0][1]
    expect(layout.n.x).toBeGreaterThan(0)
    expect(layout.a).toBeDefined()
  })

  it('已激活的路线只读：没有面板，节点拖动不保存', async () => {
    const s = await show('active')
    expect(s.container.querySelector('[data-testid=flow-palette]')).toBeNull()
    const el = node(s.container, 20)
    const c = center(el)
    await drag(el, { x: c.x + 120, y: c.y })
    await new Promise((r) => setTimeout(r, 200))
    expect(process.saveRouteLayout).not.toHaveBeenCalled()
  })
})
