import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { t } from '@/i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { mesApi } from '@/lib/api/mes/common'
import { RecipeRunCard } from './lot-trace'

afterEach(() => vi.restoreAllMocks())

describe('RecipeRunCard', () => {
  it('列出每次上机的配方版本，点开查看参数快照与规格', async () => {
    const list = vi.spyOn(mesApi, 'list').mockResolvedValue({
      data: [
        {
          id: 'r1',
          track_in_at: '2026-10-13T00:00:00Z',
          track_out_at: null,
          operation_label: 'OP10 · etch',
          equipment_label: 'EQ1 · etcher',
          recipe_label: 'RC · recipe',
          recipe_version: 2,
          chambers: 'CH-A',
          params: { temp: 350 },
          param_specs: [
            { code: 'T', name: 'temp', target: 350, lsl: 340, usl: 360 },
          ],
        },
      ],
      count: 1,
    } as never)
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const s = await render(
      <QueryClientProvider client={qc}>
        <RecipeRunCard lotId='lot-1' />
      </QueryClientProvider>
    )
    await expect.element(s.getByTestId('recipe-runs')).toBeVisible()
    expect(list).toHaveBeenCalledWith(
      'lot_recipe_run',
      expect.objectContaining({ lot: 'lot-1' })
    )
    await expect.element(s.getByText('RC v2')).toBeVisible()
    await expect.element(s.getByText('CH-A')).toBeVisible()
    await expect.element(s.getByText(t('mes.rrun.running'))).toBeVisible()
    await userEvent.click(s.getByTestId('recipe-run-params'))
    const table = s.getByTestId('recipe-run-param-table')
    await expect.element(table.getByText('temp')).toBeVisible()
    await expect.element(table.getByText('350')).toBeVisible()
    await expect.element(s.getByText('T · temp')).toBeVisible()
  })

  it('无执行记录时不显示', async () => {
    vi.spyOn(mesApi, 'list').mockResolvedValue({ data: [], count: 0 } as never)
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const s = await render(
      <QueryClientProvider client={qc}>
        <RecipeRunCard lotId='lot-1' />
      </QueryClientProvider>
    )
    await expect.poll(() => s.container.textContent).toBe('')
  })
})
