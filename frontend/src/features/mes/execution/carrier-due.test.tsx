import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { CarrierRow } from '@/lib/api/mes/execution'
import { CarrierDue } from './carrier-due'

const row = (p: Partial<CarrierRow>): CarrierRow => ({
  id: '1',
  code: 'C1',
  carrier_type: 'FOUP',
  status: 'available',
  lot_id: null,
  lot: null,
  wafers: 0,
  capacity: 25,
  use_count: 0,
  max_uses: null,
  last_cleaned_at: null,
  clean_due_at: null,
  due_state: 'ok',
  ...p,
})

describe('CarrierDue', () => {
  it('超期显示红色并带使用次数', async () => {
    const s = await render(
      <CarrierDue
        row={row({ due_state: 'overdue', use_count: 5, max_uses: 5 })}
      />
    )
    await expect.element(s.getByText('5 / 5')).toBeVisible()
    expect(s.container.querySelector('[data-state=overdue]')).not.toBeNull()
  })

  it('无上限时只显示次数', async () => {
    const s = await render(<CarrierDue row={row({ use_count: 3 })} />)
    await expect.element(s.getByText('3', { exact: true })).toBeVisible()
  })
})
