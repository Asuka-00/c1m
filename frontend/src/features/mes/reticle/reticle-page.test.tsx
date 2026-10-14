import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Toaster } from 'sonner'
import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { resetReticleMock } from '@/lib/api/mes/reticle'
import { TooltipProvider } from '@/components/ui/tooltip'
import { PageEmbedContext } from '@/components/crud/page-embed'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import ReticlePage from './reticle-page'

const wrap = (perms: string[]) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms,
  })
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <PageEmbedContext value={true}>
          <ReticlePage />
          <Toaster />
        </PageEmbedContext>
      </TooltipProvider>
    </QueryClientProvider>
  )
}

beforeEach(() => resetReticleMock())

describe('光罩页面', () => {
  it('列表 + 详情四个页签', async () => {
    const s = await render(wrap([MES_PERM.reticleWrite]))
    await expect.element(s.getByTestId('reticle-row-RTC-M1-002')).toBeVisible()
    await s.getByTestId('reticle-row-RTC-M1-002').click()
    await expect
      .element(s.getByTestId('reticle-mount-log'))
      .not.toBeInTheDocument()
    await expect.element(s.getByTestId('reticle-status-log')).toBeVisible()
    await s.getByRole('tab', { name: t('mes.reticle.tab.mounts') }).click()
    await expect
      .element(s.getByTestId('reticle-mount-log'))
      .toHaveTextContent('LITHO-01')
  })
  it('只有 write 时不显示 restore / scrap / life-reset', async () => {
    const s = await render(wrap([MES_PERM.reticleWrite]))
    await s.getByTestId('reticle-row-RTC-V1-001').click()
    await expect.element(s.getByTestId('reticle-act-hold')).toBeVisible()
    await expect
      .element(s.getByTestId('reticle-act-scrap'))
      .not.toBeInTheDocument()
    await expect
      .element(s.getByTestId('reticle-act-restore'))
      .not.toBeInTheDocument()
  })
  it('仍挂载时 restore 给出 still_mounted 友好提示', async () => {
    const s = await render(
      wrap([MES_PERM.reticleWrite, MES_PERM.reticleOverride])
    )
    await s.getByTestId('reticle-row-RTC-V1-001').click()
    await s.getByTestId('reticle-act-restore').click()
    await s.getByTestId('reticle-action-ok').click()
    await expect
      .element(s.getByText(t('mes.err.required'), { exact: true }))
      .toBeVisible()
    await userEvent.fill(s.getByTestId('reticle-reason').element(), 'pm done')
    await s.getByTestId('reticle-action-ok').click()
    await expect
      .element(
        s.getByText(
          t('mes.reticle.code.still_mounted', {
            action: t('mes.reticle.action.restore'),
          })
        )
      )
      .toBeVisible()
  })
  it('计数调整成功后列表刷新', async () => {
    const s = await render(wrap([MES_PERM.reticleWrite]))
    await s.getByTestId('reticle-row-RTC-M1-001').click()
    await s.getByTestId('reticle-act-usage').click()
    await userEvent.fill(s.getByTestId('reticle-delta').element(), '-200')
    await s.getByTestId('reticle-action-ok').click()
    await expect
      .element(s.getByText(t('mes.reticle.err.reasonIdRequired')))
      .toBeVisible()
    await userEvent.fill(s.getByTestId('reticle-reason-id').element(), 'R01')
    await s.getByTestId('reticle-action-ok').click()
    await expect
      .element(s.getByTestId('reticle-row-RTC-M1-001'))
      .toHaveTextContent('1000 / 100000')
  })
})
