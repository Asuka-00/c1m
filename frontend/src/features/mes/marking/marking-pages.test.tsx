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

/** mock：建主记录 + 首打。 */
const seedPrint = async () => {
  const r = await mockMarkingApi.create({ lot_id: 'lot1' }, 'seed-c')
  return mockMarkingApi.print(r.id, {}, 'seed-p')
}

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
      .toHaveTextContent('{date_code} {trace_code}')
    await expect
      .element(s.getByTestId('tpl-diff'))
      .toHaveTextContent(t('mes.marking.lineN', { n: 2 }))
  })
})

describe('打标模板页（D79）', () => {
  it('新建版本：复制最新版本为草稿 v3 并选中', async () => {
    const s = await render(wrap(<TemplatePage />, ALL, 'eng9'))
    await s.getByTestId('tpl-row-MK-QFN32-ACME-v2').click()
    await s.getByTestId('tpl-new-version').click()
    await expect
      .element(s.getByTestId('tpl-row-MK-QFN32-ACME-v3'))
      .toBeVisible()
    await expect.element(s.getByTestId('tpl-edit')).toBeVisible()
  })
  it('只有 marking:read + template:approve 时不显示编辑', async () => {
    const s = await render(
      wrap(
        <TemplatePage />,
        [MARKING_PERM.read, MARKING_PERM.templateApprove],
        'qa9'
      )
    )
    await s.getByTestId('tpl-row-MK-SOP8-GLOBEX-v1').click()
    await expect.element(s.getByTestId('tpl-edit')).not.toBeInTheDocument()
    await expect.element(s.getByTestId('tpl-approve')).toBeEnabled()
  })
  it('白名单外占位符前端预校验，保存禁用', async () => {
    const s = await render(wrap(<TemplatePage />, ALL))
    await s.getByTestId('tpl-row-MK-SOP8-GLOBEX-v1').click()
    await s.getByTestId('tpl-edit').click()
    await userEvent.fill(
      s.getByTestId('tpl-f-lines').element(),
      '{model}\n{date_code}'
    )
    await expect
      .element(s.getByTestId('tpl-err-placeholder'))
      .toHaveTextContent(
        t('mes.marking.err.unknownPlaceholder', { name: '{model}' })
      )
    await expect.element(s.getByTestId('tpl-save')).toBeDisabled()
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
    await userEvent.fill(s.getByTestId('mk-read-code').element(), '\u3000 ')
    await s.getByTestId('mk-act-ok').click()
    await expect
      .element(s.getByTestId('mk-err-read_code'))
      .toHaveTextContent(t('mes.marking.err.traceRequired'))
    await userEvent.fill(s.getByTestId('mk-read-code').element(), 'X-1')
    await s.getByTestId('mk-act-ok').click()
    // D79-4：填 pass 但读回不一致 → 系统改记 fail 并提示
    await expect.element(s.getByTestId('mk-ocr-diff')).toBeVisible()
    await expect.element(s.getByTestId('mk-overridden')).toBeVisible()
    await expect
      .element(
        s.getByText(
          t('mes.marking.overridden', { expected: '', read: 'X-1' }).split(
            '：'
          )[0],
          { exact: false }
        )
      )
      .toBeVisible()
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
    const r = await seedPrint()
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
  it('作废后同一批次预览可重新首打（新主记录）', async () => {
    const r = await seedPrint()
    await mockMarkingApi.void(r.id, { reason_id: 'V', comment: 'x' }, 'v')
    const s = await render(wrap(<JobPage />, ALL))
    await userEvent.fill(s.getByTestId('mk-lot').element(), 'lot1')
    await s.getByTestId('mk-preview').click()
    await s.getByTestId('mk-print').click()
    await expect.element(s.getByTestId('mk-detail')).toBeVisible()
    await expect.element(s.getByTestId('mk-voided')).not.toBeInTheDocument()
    await expect.element(s.getByTestId('mk-print-1')).toBeVisible()
  })
  it('只有 exec 没有 void 时不显示作废', async () => {
    await seedPrint()
    const s = await render(
      wrap(<JobPage />, [MARKING_PERM.read, MARKING_PERM.exec])
    )
    await s.getByTestId('mk-row-LOT-A001').click()
    await expect.element(s.getByTestId('mk-act-inspect')).toBeVisible()
    await expect.element(s.getByTestId('mk-act-void')).not.toBeInTheDocument()
  })
  it('读回码超过 128 码点前端拦截；不校验格式', async () => {
    await seedPrint()
    const s = await render(wrap(<JobPage />, ALL))
    await s.getByTestId('mk-row-LOT-A001').click()
    await s.getByTestId('mk-act-inspect').click()
    await userEvent.fill(
      s.getByTestId('mk-read-code').element(),
      'a'.repeat(129)
    )
    await s.getByTestId('mk-act-ok').click()
    await expect
      .element(s.getByTestId('mk-err-read_code'))
      .toHaveTextContent(t('mes.marking.err.readCodeTooLong', { n: 128 }))
  })
  it('列表同时显示首打时间与最近打印', async () => {
    await seedPrint()
    const s = await render(wrap(<JobPage />, ALL))
    await expect
      .element(s.getByText(t('mes.marking.col.markedAt')))
      .toBeVisible()
    await expect
      .element(s.getByText(t('mes.marking.col.lastPrintedAt')))
      .toBeVisible()
  })
})
