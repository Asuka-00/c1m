import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { ParetoChart } from './pareto-chart'

describe('ParetoChart', () => {
  it('无报废时显示空状态', async () => {
    const s = await render(<ParetoChart rows={[]} />)
    expect(s.container.querySelector('[data-testid=pareto]')).toBeNull()
  })

  it('有数据时渲染图表', async () => {
    const s = await render(
      <div style={{ width: 600 }}>
        <ParetoChart
          rows={[
            { reason: 'SC-PART', name: 'p', qty: 8, pct: 0.8, cum_pct: 0.8 },
            { reason: 'SC-SCR', name: 's', qty: 2, pct: 0.2, cum_pct: 1 },
          ]}
        />
      </div>
    )
    expect(s.container.querySelector('[data-testid=pareto]')).not.toBeNull()
  })
})
