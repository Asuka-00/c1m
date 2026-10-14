import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n, { t } from '@/i18n'
import { Toaster } from 'sonner'
import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import {
  mockMarkingApi,
  resetMarkingMock,
  setMarkingMockNow,
} from '@/lib/api/mes/marking'
import { setSiteTz } from '@/lib/site-tz'
import { TooltipProvider } from '@/components/ui/tooltip'
import { PageEmbedContext } from '@/components/crud/page-embed'
import JobPage from './job-page'
import { MARKING_PERM } from './marking-rules'
import TemplatePage from './template-page'

const wrap = (node: React.ReactNode, perms: string[], me = 'admin') => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms,
  })
  qc.setQueryData(['me'], { username: me })
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <PageEmbedContext value={true}>
          {node}
          <Toaster />
        </PageEmbedContext>
      </TooltipProvider>
    </QueryClientProvider>
  )
}

const ALL = Object.values(MARKING_PERM)

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
  resetMarkingMock()
  setSiteTz('Asia/Taipei')
})

describe('打标模板页', () => {
  it('起草人自己的草稿：审批按钮禁用并提示', async () => {
    const s = await render(wrap(<TemplatePage />, ALL, 'admin'))
    await s.getByTestId('tpl-row-MK-SOP8-GLOBEX-v1').click()
    await expect.element(s.getByTestId('tpl-approve')).toBeDisabled()
    await expect.element(s.getByTestId('tpl-self-hint')).toBeVisible()
  })
  it('他人审批后状态变为已批准', async () => {
    const s = await render(wrap(<TemplatePage />, ALL, 'qa9'))
    await s.getByTestId('tpl-row-MK-SOP8-GLOBEX-v1').click()
    await s.getByTestId('tpl-approve').click()
    await expect
      .element(s.getByTestId('tpl-row-MK-SOP8-GLOBEX-v1'))
      .toHaveTextContent(t('mes.marking.status.approved'))
  })
  it('只有 read 时不显示编辑和审批', async () => {
    const s = await render(wrap(<TemplatePage />, [MARKING_PERM.read]))
    await s.getByTestId('tpl-row-MK-SOP8-GLOBEX-v1').click()
    await expect.element(s.getByTestId('tpl-edit')).not.toBeInTheDocument()
    await expect.element(s.getByTestId('tpl-approve')).not.toBeInTheDocument()
  })
  it('版本对比列出逐行差异', async () => {
    const s = await render(wrap(<TemplatePage />, ALL))
    await s.getByTestId('tpl-row-MK-QFN32-ACME-v2').click()
    await userEvent.selectOptions(s.getByTestId('tpl-compare').element(), 't1')
    await expect
      .element(s.getByTestId('tpl-diff'))
      .toHaveTextContent('{yyww} {trace}')
    await expect
      .element(s.getByTestId('tpl-diff'))
      .toHaveTextContent(t('mes.marking.lineN', { n: 2 }))
  })
})

describe('打标作业页', () => {
  beforeEach(() => setMarkingMockNow(() => new Date()))

  it('没有已批准模板时提示', async () => {
    const s = await render(wrap(<JobPage />, ALL))
    await userEvent.fill(s.getByTestId('mk-lot').element(), 'lot3')
    await s.getByTestId('mk-preview').click()
    await expect
      .element(s.getByTestId('mk-preview-err'))
      .toHaveTextContent(t('mes.marking.code.marking_template_missing'))
  })
  it('预览 → 打印 → 检验不合格（OCR 差异）→ 重打必须填原因 → seq 2', async () => {
    const s = await render(wrap(<JobPage />, ALL))
    await userEvent.fill(s.getByTestId('mk-lot').element(), 'lot1')
    await s.getByTestId('mk-preview').click()
    await expect
      .element(s.getByTestId('mk-preview-lines'))
      .toHaveTextContent('FS3201')
    await s.getByTestId('mk-print').click()
    await expect.element(s.getByTestId('mk-detail')).toBeVisible()
    await expect.element(s.getByTestId('mk-print-1')).toBeVisible()
    // 检验：读回码格式错误前端拦
    await s.getByTestId('mk-act-inspect').click()
    await userEvent.fill(s.getByTestId('mk-read-code').element(), 'ab')
    await s.getByTestId('mk-act-ok').click()
    await expect
      .element(s.getByTestId('mk-err-read_code'))
      .toHaveTextContent(t('mes.marking.err.trace_pattern'))
    await userEvent.fill(s.getByTestId('mk-read-code').element(), 'X-1')
    await s.getByTestId('mk-act-ok').click()
    await expect.element(s.getByTestId('mk-ocr-diff')).toBeVisible()
    await expect.element(s.getByTestId('mk-act-reprint')).toBeEnabled()
    // 重打：原因必填
    await s.getByTestId('mk-act-reprint').click()
    await s.getByTestId('mk-act-ok').click()
    await expect
      .element(s.getByTestId('mk-err-reason_id'))
      .toHaveTextContent(t('mes.marking.err.reason_idRequired'))
    await expect.element(s.getByTestId('mk-err-comment')).toBeVisible()
    await userEvent.fill(s.getByTestId('mk-reason-id').element(), 'RP01')
    await userEvent.fill(s.getByTestId('mk-comment').element(), '字迹模糊')
    await s.getByTestId('mk-act-ok').click()
    await expect
      .element(s.getByTestId('mk-print-reason-2'))
      .toHaveTextContent('字迹模糊')
    await expect.element(s.getByTestId('insp-pending').first()).toBeVisible()
  })
  it('作废需要二次确认，作废后按钮全部禁用', async () => {
    const r = await mockMarkingApi.mark({ lot_id: 'lot1' }, 'seed')
    const s = await render(wrap(<JobPage />, ALL))
    await s.getByTestId('mk-row-LOT-A001').click()
    await s.getByTestId('mk-act-void').click()
    await userEvent.fill(s.getByTestId('mk-reason-id').element(), 'V01')
    await userEvent.fill(s.getByTestId('mk-comment').element(), '错批')
    await s.getByTestId('mk-act-ok').click()
    await expect
      .element(s.getByTestId('mk-void-confirm'))
      .toHaveTextContent(r.trace_code)
    await s.getByTestId('mk-act-ok').click()
    await expect.element(s.getByTestId('mk-voided')).toBeVisible()
    await expect.element(s.getByTestId('mk-act-void')).toBeDisabled()
    await expect.element(s.getByTestId('mk-act-inspect')).toBeDisabled()
    await expect.element(s.getByTestId('mk-act-reprint')).toBeDisabled()
  })
})
