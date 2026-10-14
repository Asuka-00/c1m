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

function args(rows: LineDraft[]) {
  return { bom: BOM, desc: 'v4', rows }
}

afterEach(() => vi.restoreAllMocks())

describe('saveDraft 整单提交（PUT /mes/bom/{id}/lines）', () => {
  it('一次提交全部明细和替代料，只带白名单字段；删除的行不带；错误下标换回编辑框下标', async () => {
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
    const err = await saveDraft(args([removed, toLineDraft(LINE), prod])).catch(
      (e) => e
    )
    expect(err).toBeInstanceOf(BomSaveError)
    const [id, lines] = put.mock.calls[0]
    expect(id).toBe('b4')
    expect(lines).toEqual([
      {
        line_no: 10,
        component_type: 'material',
        material_id: 'm1',
        qty: '0.3',
        uom_id: 'g',
        per_basis: 'die',
        scrap_rate: 0.02,
        consume_mode: 'issue',
        substitutes: [
          { material_id: 'm2', priority: 1 },
          { material_id: 'm3', priority: 2 },
        ],
      },
      {
        line_no: 20,
        component_type: 'product',
        component_product_id: 'p-wafer',
        qty: '0.3',
        uom_id: 'g',
        per_basis: 'die',
        scrap_rate: 0.02,
        consume_mode: 'issue',
        substitutes: [],
      },
    ])
    expect(err.lineMap).toEqual([1, 2])
  })

  it('行号留空时按顺序接在最大行号后面', async () => {
    const put = vi.spyOn(bomApi, 'replaceLines').mockResolvedValue({
      bom: null,
      lines: [],
    } as never)
    const blank = (key: string): LineDraft => ({
      ...toLineDraft(LINE),
      id: undefined,
      key,
      line_no: '',
    })
    await saveDraft(args([blank('a'), toLineDraft(LINE), blank('b')]))
    expect(put.mock.calls[0][1].map((l) => l.line_no)).toEqual([20, 10, 30])
  })

  it('删光所有行时提交 {lines: []} 清空；说明改了先保存主表', async () => {
    const put = vi.spyOn(bomApi, 'replaceLines').mockResolvedValue({} as never)
    const upd = vi.spyOn(bomApi, 'update').mockResolvedValue(BOM)
    await saveDraft({
      bom: BOM,
      desc: 'v4 new',
      rows: [{ ...toLineDraft(LINE), removed: true }],
    })
    expect(upd).toHaveBeenCalledWith('b4', 'v4 new')
    expect(put).toHaveBeenCalledWith('b4', [])
  })

  it('主表说明保存失败：lineMap 为 null，不提交明细', async () => {
    const put = vi.spyOn(bomApi, 'replaceLines')
    vi.spyOn(bomApi, 'update').mockRejectedValue(new Error('x'))
    const err = await saveDraft({
      bom: BOM,
      desc: 'changed',
      rows: [toLineDraft(LINE)],
    }).catch((e) => e)
    expect(err.lineMap).toBeNull()
    expect(put).not.toHaveBeenCalled()
  })
})
