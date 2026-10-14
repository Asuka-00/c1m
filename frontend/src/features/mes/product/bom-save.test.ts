import { afterEach, describe, expect, it, vi } from 'vitest'
import { bomApi, type Bom, type BomLine } from '@/lib/api/mes/bom'
import {
  BomSaveError,
  type LineDraft,
  saveDraft,
  toLineDraft,
} from './bom-save'

const BOM: Bom = {
  id: 'b4',
  product_id: 'p1',
  version: 4,
  status: 'draft',
  effective_at: null,
  confirmed_by: null,
  confirmed_at: null,
  copied_from_id: null,
  copied_from_label: null,
  description: 'v4',
  created_at: '2026-10-14T05:58:05Z',
  updated_at: '2026-10-14T05:58:05Z',
}
const LINE: BomLine = {
  id: 'l10',
  bom_id: 'b4',
  line_no: 10,
  component_type: 'material',
  material_id: 'm1',
  material_label: 'FED-WIRE',
  component_product_id: null,
  component_product_label: null,
  qty: 0.3,
  uom_id: 'g',
  uom_label: 'g',
  per_basis: 'die',
  scrap_rate: 0.02,
  consume_mode: 'issue',
  remark: null,
  substitutes: [
    {
      id: 's1',
      bom_line_id: 'l10',
      material_id: 'm2',
      material_label: 'A',
      priority: 1,
    },
    {
      id: 's2',
      bom_line_id: 'l10',
      material_id: 'm3',
      material_label: 'B',
      priority: 2,
    },
  ],
}

function args(rows: LineDraft[], lines: BomLine[] = [LINE]) {
  return {
    bom: BOM,
    desc: 'v4',
    rows,
    saved: new Map(lines.map((l) => [l.id, toLineDraft(l)])),
    patchRow: vi.fn(),
  }
}

function spyAll() {
  const calls: string[] = []
  vi.spyOn(bomApi, 'removeSubstitute').mockImplementation(async (id) => {
    calls.push(`del-sub ${id}`)
  })
  vi.spyOn(bomApi, 'addSubstitute').mockImplementation(async (line, b) => {
    calls.push(`add-sub ${line} ${b.material_id} ${b.priority}`)
    return {
      id: `new-${b.material_id}`,
      bom_line_id: line,
      material_id: b.material_id!,
      material_label: null,
      priority: b.priority,
    }
  })
  vi.spyOn(bomApi, 'updateLine').mockImplementation(async (id, b) => {
    calls.push(`upd-line ${id} ${JSON.stringify(b)}`)
    return LINE
  })
  vi.spyOn(bomApi, 'addLine').mockImplementation(async (_b, body) => {
    calls.push(`add-line ${body.line_no}`)
    return { ...LINE, id: `l${body.line_no}` }
  })
  vi.spyOn(bomApi, 'removeLine').mockImplementation(async (id) => {
    calls.push(`del-line ${id}`)
  })
  return calls
}

afterEach(() => vi.restoreAllMocks())

describe('saveDraft 逐行模式（后端暂无整单接口）', () => {
  it('互换替代料优先级：先删后建，明细没改不发请求', async () => {
    const calls = spyAll()
    const d = toLineDraft(LINE)
    d.subs = [
      { ...d.subs[0], priority: '2' },
      { ...d.subs[1], priority: '1' },
    ]
    await saveDraft(args([d]), 'perLine')
    expect(calls).toEqual([
      'del-sub s1',
      'del-sub s2',
      'add-sub l10 m2 2',
      'add-sub l10 m3 1',
    ])
  })

  it('改成半成品：先删替代料，再改明细，只传半成品字段', async () => {
    const calls = spyAll()
    const d: LineDraft = {
      ...toLineDraft(LINE),
      component_type: 'product',
      component_product_id: 'p-wafer',
    }
    await saveDraft(args([d]), 'perLine')
    expect(calls).toEqual([
      'del-sub s1',
      'del-sub s2',
      'upd-line l10 {"component_type":"product","component_product_id":"p-wafer"}',
    ])
  })

  it('新行：先建明细再建替代料；替代料失败时定位到该行该条，重试不重复建明细', async () => {
    const calls = spyAll()
    const d: LineDraft = {
      ...toLineDraft(LINE),
      key: 'n',
      id: undefined,
      line_no: '20',
      subs: [
        { key: 'x', material_id: 'm9', material_label: null, priority: '1' },
      ],
    }
    vi.mocked(bomApi.addSubstitute).mockRejectedValueOnce(new Error('boom'))
    const a = args([d], [])
    const err = await saveDraft(a, 'perLine').catch((e) => e)
    expect(err).toBeInstanceOf(BomSaveError)
    expect([err.line, err.sub]).toEqual([0, 0])
    expect(a.patchRow).toHaveBeenCalledWith(
      0,
      expect.objectContaining({ id: 'l20' })
    )
    // 页面把 id 回写到编辑框后重试
    await saveDraft({ ...a, rows: [{ ...d, id: 'l20' }] }, 'perLine')
    expect(calls.filter((c) => c.startsWith('add-line'))).toEqual([
      'add-line 20',
    ])
    expect(calls[calls.length - 1]).toBe('add-sub l20 m9 1')
  })
})

describe('saveDraft 整单模式（PUT /mes/bom/{id}/lines）', () => {
  it('一次提交全部明细和替代料，删除的行不带；错误下标换回编辑框下标', async () => {
    const put = vi
      .spyOn(bomApi, 'replaceLines')
      .mockRejectedValue(new Error('422'))
    const removed = { ...toLineDraft(LINE), removed: true }
    const prod: LineDraft = {
      ...toLineDraft(LINE),
      id: undefined,
      key: 'p',
      line_no: '20',
      component_type: 'product',
      component_product_id: 'p-wafer',
    }
    const err = await saveDraft(
      args([removed, toLineDraft(LINE), prod]),
      'replace'
    ).catch((e) => e)
    const [, lines] = put.mock.calls[0]
    expect(lines).toHaveLength(2)
    expect(lines[0].substitutes).toEqual([
      { material_id: 'm2', priority: 1 },
      { material_id: 'm3', priority: 2 },
    ])
    expect(lines[1]).toMatchObject({
      component_type: 'product',
      component_product_id: 'p-wafer',
      substitutes: [],
    })
    expect(lines[1]).not.toHaveProperty('material_id')
    expect(err.lineMap).toEqual([1, 2])
  })
})
