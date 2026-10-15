import i18n, { t } from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { CheckResult } from '@/lib/api/mes/execution'
import { MarkingRecordLink } from '@/features/mes/execution/exec-parts'

const r = (ctx: Record<string, unknown>) =>
  ({
    check_type: 'marking_inspection',
    result: 'block',
    ctx,
  }) as unknown as CheckResult

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('出站拦截跳转到打标记录', () => {
  it('有 marking_id 时给出链接', async () => {
    const s = await render(
      <MarkingRecordLink r={r({ reason: 'fail', marking_id: 'm 1' })} />
    )
    const a = s.getByTestId('marking-record-link')
    await expect.element(a).toHaveTextContent(t('mes.marking.openRecord'))
    await expect.element(a).toHaveAttribute('href', '/mes/marking?record=m%201')
  })
  it('not_marked 没有 marking_id 时不显示', async () => {
    const s = await render(
      <MarkingRecordLink r={r({ reason: 'not_marked' })} />
    )
    await expect
      .element(s.getByTestId('marking-record-link'))
      .not.toBeInTheDocument()
  })
})
