import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { execApi } from '@/lib/api/mes/execution'
import { WaferStatusCard } from './lot-trace'

describe('WaferStatusCard', () => {
  it('按槽位显示晶圆，点击后查看晶圆履历', async () => {
    vi.spyOn(execApi, 'waferStatus').mockResolvedValue({
      lot: 'L1',
      carrier: 'FOUP-1',
      capacity: 3,
      slots: [
        { slot: 1, wafer: { id: 'w1', code: 'L1-01', status: 'waiting' } },
        { slot: 2, wafer: null },
        { slot: 3, wafer: { id: 'w3', code: 'L1-03', status: 'scrapped' } },
      ],
      units: [],
    })
    const hist = vi
      .spyOn(execApi, 'waferHistory')
      .mockResolvedValue([
        { id: 'h1', action: 'start', at: '2026-10-13T00:00:00Z', qty: 1 },
      ])
    const qc = new QueryClient()
    const { getByTestId } = await render(
      <QueryClientProvider client={qc}>
        <WaferStatusCard lotId='lot-1' />
      </QueryClientProvider>
    )
    await expect.element(getByTestId('wafer-status')).toBeInTheDocument()
    expect(getByTestId('wafer-cell').elements()).toHaveLength(2)
    expect(getByTestId('empty-slot').elements()).toHaveLength(1)
    await userEvent.click(getByTestId('wafer-cell').first())
    await expect.element(getByTestId('timeline')).toBeInTheDocument()
    expect(hist).toHaveBeenCalledWith('w1')
  })
})
