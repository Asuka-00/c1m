import i18n, { t } from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { MesEntity } from '@/lib/api/mes/common'
import type { CheckResult } from '@/lib/api/mes/execution'
import { qualExpiringMock, visibleExpiring } from '@/lib/api/mes/qual-expiring'
import { CELLS } from '@/features/mes/common/row-rules'
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
    await expect
      .element(s.getByText(t('mes.qual.lastDay')).first())
      .toBeVisible()
    await expect
      .element(s.getByText(t('mes.qual.warnDays', { n: 30 })))
      .toBeVisible()
  })
})

describe('D64 补充：warn_days 元数据与汇总排序', () => {
  const ymd = (d: number) => {
    const x = new Date()
    x.setDate(x.getDate() + d)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${x.getFullYear()}-${p(x.getMonth() + 1)}-${p(x.getDate())}`
  }
  let k = 0
  const cell = async (warn: number | undefined, days: number) => {
    const id = `qc${k++}`
    const e = { code: 'operator_qual', warn_days: warn } as unknown as MesEntity
    const s = await render(
      <div data-testid={id}>
        {CELLS.operator_qual.expires_on(
          { id: 'q', is_active: true, expires_on: ymd(days) },
          e
        )}
      </div>
    )
    return s.getByTestId(id)
  }

  it('列表页读元数据 warn_days，读不到用 30', async () => {
    await expect
      .element(await cell(10, 20))
      .not.toHaveTextContent(t('mes.due.expiring'))
    await expect
      .element(await cell(undefined, 20))
      .toHaveTextContent(t('mes.due.expiring'))
  })

  it('保持后端顺序、兜底过滤已过期；示例数据已按后端规则排好', () => {
    const m = qualExpiringMock()
    expect(m.rows.every((r) => r.days_left >= 0)).toBe(true)
    const sorted = [...m.rows].sort(
      (a, b) => a.days_left - b.days_left || (a.username < b.username ? -1 : 1)
    )
    expect(m.rows).toEqual(sorted)
    const v = visibleExpiring([
      { ...m.rows[0], username: 'b', days_left: 3 },
      { ...m.rows[0], username: 'x', days_left: -1 },
      { ...m.rows[0], username: 'a', days_left: 3 },
    ])
    expect(v.map((r) => r.username)).toEqual(['b', 'a'])
  })

  it('页面不显示已过期行', async () => {
    const m = qualExpiringMock()
    const s = await render(
      <QualExpiringView
        data={{
          ...m,
          rows: [{ ...m.rows[0], username: 'gone', days_left: -2 }, ...m.rows],
        }}
      />
    )
    expect(s.container.textContent).not.toContain('gone')
  })
})
