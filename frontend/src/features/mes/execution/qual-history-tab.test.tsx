import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import {
  mockQualWriteApi,
  resetQualHistoryMock,
} from '@/lib/api/mes/qual-history'
import { qualChanges } from './qual-history-format'
import { QualHistoryTab } from './qual-history-tab'

const wrap = (id: string) => (
  <QueryClientProvider
    client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
  >
    <QualHistoryTab row={{ id } as never} />
  </QueryClientProvider>
)
beforeEach(() => resetQualHistoryMock())
afterEach(async () => {
  resetQualHistoryMock()
  await i18n.changeLanguage('zh-CN')
})

describe('资质履历页签', () => {
  it('显示停用行的原因、说明，三语动作文案', async () => {
    await mockQualWriteApi.update(
      'q1',
      { is_active: false, reason_id: 'RQ1', comment: '离岗' },
      'tab-1'
    )
    const s = await render(wrap('q1'))
    const row = s.getByTestId('qual-log-deactivated')
    await expect.element(row).toHaveTextContent('离岗')
    await expect.element(row).toHaveTextContent('RQ1')
    await expect
      .element(row)
      .toHaveTextContent(t('mes.qualHistory.action.deactivated'))
    await expect.element(s.getByTestId('qual-log-granted')).toBeVisible()
    for (const lng of ['en', 'ja']) {
      await i18n.changeLanguage(lng)
      for (const a of [
        'granted',
        'renewed',
        'changed',
        'deactivated',
        'reactivated',
        'expired',
      ])
        expect(i18n.exists(`mes.qualHistory.action.${a}`)).toBe(true)
    }
  })
  it('资质不存在显示 404 文案', async () => {
    const s = await render(wrap('nope'))
    await expect.element(s.getByTestId('qual-history-error')).toBeVisible()
  })
  it('变更摘要', () => {
    expect(
      qualChanges({
        before: { expires_on: '2026-10-20' },
        after: { expires_on: '2027-10-20' },
      })
    ).toBe(`${t('mes.qualHistory.field.expires_on')}: 2026-10-20 → 2027-10-20`)
  })
})
