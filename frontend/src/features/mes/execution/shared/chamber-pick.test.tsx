import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { ChamberPick } from './chamber-pick'

const opt = (id: string, state: string) => ({
  id,
  code: `EQ-${id}`,
  name: id,
  state,
  category: 'SBY',
  color: null,
})

describe('ChamberPick', () => {
  it('无腔体时不渲染', async () => {
    const s = await render(
      <ChamberPick options={[]} value={[]} onChange={() => {}} />
    )
    expect(s.container.querySelector('[data-testid=chambers]')).toBeNull()
  })

  it('勾选 / 取消腔体', async () => {
    const fn = vi.fn()
    const s = await render(
      <ChamberPick
        options={[opt('PM1', 'SBY-IDLE'), opt('PM2', 'UDT-DOWN')]}
        value={['PM2']}
        onChange={fn}
      />
    )
    await expect.element(s.getByText('UDT-DOWN')).toBeVisible()
    await s.getByRole('checkbox', { name: 'EQ-PM1' }).click()
    expect(fn).toHaveBeenLastCalledWith(['PM2', 'PM1'])
    await s.getByRole('checkbox', { name: 'EQ-PM2' }).click()
    expect(fn).toHaveBeenLastCalledWith([])
  })
})
