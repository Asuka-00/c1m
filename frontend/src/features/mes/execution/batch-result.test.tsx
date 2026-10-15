import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { BatchResult } from './batch-result'

describe('BatchResult', () => {
  it('显示成功、阻断与错误', async () => {
    const s = await render(
      <BatchResult
        items={[
          { lot_id: '1', code: 'L1', ok: true, results: [] },
          {
            lot_id: '2',
            code: 'L2',
            results: [
              {
                check_type: 'batch_same_step',
                rule_id: 'r',
                rule_code: 'CR-BATCH',
                rule_name: null,
                plan_code: null,
                severity: 'block',
                result: 'block',
                applicable: true,
                message: 'lots are at different steps',
                overridable: true,
              },
            ],
          },
          {
            lot_id: '3',
            code: 'L3',
            ok: false,
            error: [{ msg: 'lot: on hold' }],
          },
        ]}
      />
    )
    await expect.element(s.getByText('L1')).toBeVisible()
    await expect
      .element(s.getByText('CR-BATCH: lots are at different steps'))
      .toBeVisible()
    await expect.element(s.getByText('lot: on hold')).toBeVisible()
    expect(s.container.querySelectorAll('li')).toHaveLength(3)
  })
})
