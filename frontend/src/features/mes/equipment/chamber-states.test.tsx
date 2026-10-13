import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { ChamberStates } from './chamber-states'

const unit = (code: string, next: number) => ({
  id: code,
  code,
  name: code,
  is_active: true,
  state: {
    id: 's',
    code: 'SBY-IDLE',
    name: 'Idle',
    category: 'SBY',
    color: null,
  },
  next: Array.from({ length: next }, (_, i) => ({
    id: String(i),
    code: 'UDT',
    name: 'down',
    reason_required: false,
  })),
})

describe('ChamberStates', () => {
  it('列出腔体并可改状态', async () => {
    const fn = vi.fn()
    const s = await render(
      <ChamberStates
        main='ETC01'
        chambers={[unit('ETC01-PM1', 1), unit('ETC01-PM2', 0)]}
        canChange
        onChange={fn}
      />
    )
    await expect.element(s.getByText('ETC01-PM1')).toBeVisible()
    await s.getByTestId('e10-ETC01-PM1').click()
    expect(fn).toHaveBeenCalledWith(
      expect.objectContaining({ code: 'ETC01-PM1' })
    )
    await expect.element(s.getByTestId('e10-ETC01-PM2')).toBeDisabled()
  })
})
