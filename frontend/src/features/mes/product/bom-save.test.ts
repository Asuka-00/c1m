import { t } from '@/i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { bomApi, type Bom, type BomLine } from '@/lib/api/mes/bom'
import {
  BomSaveError,
  type LineDraft,
  saveDraft,
  validateRows,
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
        scrap_rate: '0.02',
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
        scrap_rate: '0.02',
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

describe('validateRows（D49）', () => {
  const row = (qty: string, scrap_rate: string): LineDraft => ({
    ...toLineDraft(LINE),
    qty,
    scrap_rate,
  })
  const errs = (qty: string, scrap: string) =>
    validateRows([row(qty, scrap)]).map((e) => `${e.field}:${e.message}`)

  it('qty：必须大于 0，最多 6 位小数（去末尾零后算）', () => {
    expect(errs('0.000001', '0')).toEqual([])
    expect(errs('1.5000000', '0')).toEqual([])
    expect(errs('0', '0')).toEqual([`qty:${t('mes.bomTab.err.positive')}`])
    expect(errs('-1', '0')).toEqual([`qty:${t('mes.bomTab.err.positive')}`])
    expect(errs('abc', '0')).toEqual([`qty:${t('mes.bomTab.err.notNumber')}`])
    expect(errs('0.0000001', '0')).toEqual([
      `qty:${t('mes.bomTab.err.tooManyDecimals', { n: 6 })}`,
    ])
    expect(errs('1e-7', '0')).toEqual([
      `qty:${t('mes.bomTab.err.tooManyDecimals', { n: 6 })}`,
    ])
    expect(errs('1e-6', '0')).toEqual([])
  })

  it('scrap_rate：0 和 1 合法，<0、>1 报错，最多 4 位小数', () => {
    expect(errs('1', '0')).toEqual([])
    expect(errs('1', '1')).toEqual([])
    expect(errs('1', '1.0000')).toEqual([])
    expect(errs('1', '0.0001')).toEqual([])
    const range = `scrap_rate:${t('mes.bomTab.err.scrapRange')}`
    expect(errs('1', '-0.01')).toEqual([range])
    expect(errs('1', '1.0001')).toEqual([range])
    expect(errs('1', '1e1')).toEqual([range])
    expect(errs('1', '0.00001')).toEqual([
      `scrap_rate:${t('mes.bomTab.err.tooManyDecimals', { n: 4 })}`,
    ])
    expect(errs('1', 'x')).toEqual([
      `scrap_rate:${t('mes.bomTab.err.notNumber')}`,
    ])
  })

  it('删除的行不查；校验不过不发请求', async () => {
    expect(validateRows([{ ...row('-1', '2'), removed: true }])).toEqual([])
    const put = vi.spyOn(bomApi, 'replaceLines')
    const err = await saveDraft(args([row('1e-7', '0')])).catch((e) => e)
    expect(err.local).toHaveLength(1)
    expect(put).not.toHaveBeenCalled()
  })

  it('提交去掉末尾零的字符串（含科学计数法换算）', async () => {
    const put = vi.spyOn(bomApi, 'replaceLines').mockResolvedValue({} as never)
    await saveDraft(args([row('1.5000000', '1.5e-2')]))
    expect(put.mock.calls[0][1][0]).toMatchObject({
      qty: '1.5',
      scrap_rate: '0.015',
    })
  })
})

describe('D50：十进制字段既能是数字也能是字符串', () => {
  it('回填编辑框不经浮点：字符串原样（去末尾零），数字不出指数', () => {
    const s = toLineDraft({ ...LINE, qty: '0.000125000', scrap_rate: '0.0200' })
    expect([s.qty, s.scrap_rate]).toEqual(['0.000125', '0.02'])
    const n = toLineDraft({ ...LINE, qty: 1e-6, scrap_rate: 0 })
    expect([n.qty, n.scrap_rate]).toEqual(['0.000001', '0'])
    const big = toLineDraft({ ...LINE, qty: '123456789012.123456' })
    expect(big.qty).toBe('123456789012.123456')
  })
})
