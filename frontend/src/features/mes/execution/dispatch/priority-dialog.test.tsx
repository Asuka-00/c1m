import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { t } from '@/i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { mesApi } from '@/lib/api/mes/common'
import { execApi, type ExecContext } from '@/lib/api/mes/execution'
import { PriorityDialog } from './priority-dialog'

afterEach(() => vi.restoreAllMocks())

describe('优先级变更对话框', () => {
  it('不列出当前优先级，急件带火焰；提交新优先级与备注', async () => {
    vi.spyOn(mesApi, 'list').mockResolvedValue({
      data: [
        { id: 'P0', code: 'NORMAL', name: 'normal', is_hot: false },
        { id: 'P1', code: 'HOT', name: 'hot lot', is_hot: true },
      ],
      count: 2,
    } as never)
    const set = vi.spyOn(execApi, 'priority').mockResolvedValue({} as never)
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    qc.setQueryData(['mes', 'meta', 'auto'], {
      modules: [],
      entities: [],
      enums: {},
      perms: [],
    })
    const cx = { lot: { id: 'L1', code: 'LOT1', priority_id: 'P0' } }
    const s = await render(
      <QueryClientProvider client={qc}>
        <PriorityDialog
          cx={cx as unknown as ExecContext}
          open
          canOverride={false}
          onOpenChange={() => {}}
        />
      </QueryClientProvider>
    )
    const submit = s.getByRole('button', { name: t('mes.prio.title') })
    await expect.element(submit).toBeDisabled()
    await s.getByRole('combobox', { name: t('mes.prio.new') }).click()
    await expect
      .poll(() =>
        [...document.querySelectorAll('[role=option]')].map(
          (o) => o.textContent
        )
      )
      .toEqual(['🔥 HOT · hot lot'])
    await userEvent.click(s.getByRole('option', { name: '🔥 HOT · hot lot' }))
    await userEvent.fill(s.getByLabelText(t('mes.exec.comment')), 'rush')
    await userEvent.click(submit)
    await expect
      .poll(() => set.mock.calls[0])
      .toEqual(['L1', { priority_id: 'P1', comment: 'rush' }])
  })
})
