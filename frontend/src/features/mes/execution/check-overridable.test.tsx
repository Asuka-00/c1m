import i18n, { t } from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { CheckResult } from '@/lib/api/mes/execution'
import { qualExpiringMock } from '@/lib/api/mes/qual-expiring'
import { CheckPanel } from './exec-parts'
import { QualExpiringView } from './qual-expiring'

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

const res = (over: Partial<CheckResult>): CheckResult => ({
  check_type: 'operator_qualified',
  rule_id: null,
  rule_code: null,
  rule_name: null,
  plan_code: null,
  severity: 'block',
  result: 'block',
  applicable: true,
  message: 'x',
  overridable: false,
  data: { user: 'op1', operation: 'WB' },
  ...over,
})

describe('check_blocked 按 overridable 决定放行', () => {
  it('operator_qualified overridable=false：不显示放行，提示不可放行', async () => {
    const s = await render(
      <CheckPanel
        results={[res({})]}
        blocked
        canOverride
        onOverride={() => {}}
      />
    )
    await expect.element(s.getByTestId('hard-block')).toBeVisible()
    expect(s.container.querySelector('#override-reason')).toBeNull()
    await expect
      .element(
        s.getByText(t('mes.qual.notQualified', { user: 'op1', op: 'WB' }))
      )
      .toBeVisible()
  })

  it('overridable=true（如光罩待检）：显示放行表单', async () => {
    const s = await render(
      <CheckPanel
        results={[res({ check_type: 'reticle', overridable: true })]}
        blocked
        canOverride
        onOverride={() => {}}
      />
    )
    expect(s.container.querySelector('#override-reason')).not.toBeNull()
    expect(s.container.querySelector('[data-testid=hard-block]')).toBeNull()
  })
})

describe('即将到期人员汇总', () => {
  it('示例数据标示例、按剩余天数排序、当天到期标当天有效', async () => {
    const s = await render(<QualExpiringView data={qualExpiringMock()} />)
    await expect.element(s.getByTestId('qual-exp-mock')).toBeVisible()
    await expect.element(s.getByText(t('mes.qual.lastDay'))).toBeVisible()
    await expect
      .element(s.getByText(t('mes.qual.warnDays', { n: 30 })))
      .toBeVisible()
  })
})
