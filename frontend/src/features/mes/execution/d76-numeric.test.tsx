import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { CarrierRow } from '@/lib/api/mes/execution'
import { mulDecimal } from '@/lib/decimal'
import {
  type LineDraft,
  SCRAP_DECIMALS,
  validateRows,
} from '@/features/mes/product/bom-save'
import { CarrierDue } from './carrier-due'
import { toolLifeLevel, warnRatio } from './tool-life'

const carrier = (o: Partial<CarrierRow>): CarrierRow => ({
  id: 'c',
  code: 'C1',
  carrier_type: null,
  status: 'available',
  lot_id: null,
  lot: null,
  wafers: 0,
  capacity: 25,
  use_count: 3,
  max_uses: 100,
  last_cleaned_at: null,
  clean_due_at: null,
  due_state: 'ok',
  ...o,
})

describe('D76 专用接口定点字符串', () => {
  it('mulDecimal 精确相乘', () => {
    expect(mulDecimal('0.1', '3')).toBe('0.3')
    expect(mulDecimal('10.000000', '0.9')).toBe('9')
    expect(mulDecimal(95, '0.01')).toBe('0.95')
    expect(mulDecimal('-1.5', '2')).toBe('-3')
    expect(mulDecimal('x', 1)).toBeNull()
  })

  it('预警线不用浮点：0.7 × 0.1 的边界', () => {
    // 浮点 0.7 * 0.1 = 0.06999999999999999，'0.07' 会被误判为 warn 之上/之下
    expect(toolLifeLevel('0.07', '0.7', '0.1')).toBe('warn')
    expect(toolLifeLevel('0.069999', '0.7', '0.1')).toBe('ok')
    expect(toolLifeLevel(9, 10, 0.9)).toBe('warn')
    expect(toolLifeLevel('130.000000', '130', '0.9')).toBe('over')
  })

  it('warn_pct 字符串或数字都兼容，精确 ÷100', () => {
    expect(warnRatio({ warn_pct: '85' })).toBe('0.85')
    expect(warnRatio({ warn_pct: 85 })).toBe('0.85')
    expect(warnRatio({ warn_pct: '0' })).toBe('0.9')
    expect(warnRatio({ warn_ratio: '1.5', warn_pct: 80 })).toBe('0.8')
  })

  it('载具 max_uses / use_count：数字和字符串显示一致', async () => {
    const a = await render(<CarrierDue row={carrier({})} />)
    expect(a.container.textContent).toContain('3 / 100')
    a.unmount()
    const b = await render(
      <CarrierDue
        row={carrier({ use_count: '3.000000', max_uses: '100.000000' })}
      />
    )
    expect(b.container.textContent).toContain('3 / 100')
    b.unmount()
    const c = await render(
      <CarrierDue row={carrier({ max_uses: '0.000000' })} />
    )
    expect(c.container.textContent).not.toContain('/')
  })

  it('scrap_rate 按 4 位小数', () => {
    expect(SCRAP_DECIMALS).toBe(4)
    const row = (scrap_rate: string) =>
      ({
        key: 'k',
        line_no: '10',
        component_type: 'material',
        material_id: 'm',
        material_label: null,
        component_product_id: null,
        component_product_label: null,
        qty: '1',
        uom_id: 'u',
        per_basis: 'per_unit',
        scrap_rate,
        consume_mode: 'manual',
        subs: [],
      }) as LineDraft
    expect(validateRows([row('0.0125')])).toEqual([])
    expect(validateRows([row('0.01255')]).map((e) => e.field)).toEqual([
      'scrap_rate',
    ])
  })
})
