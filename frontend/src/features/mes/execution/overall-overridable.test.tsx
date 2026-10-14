import { AxiosError, AxiosHeaders } from 'axios'
import { t } from '@/i18n'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import {
  blockedOverridable,
  isHardBlock,
  type CheckResult,
} from '@/lib/api/mes/execution'
import { CheckPanel } from './exec-parts'

const r = (x: Partial<CheckResult>): CheckResult => ({
  check_type: 'eqp_state',
  rule_id: null,
  rule_code: null,
  rule_name: null,
  plan_code: null,
  severity: 'block',
  result: 'block',
  applicable: true,
  message: 'blocked',
  overridable: true,
  ...x,
})

const ax = (status: number, detail: unknown) => {
  const e = new AxiosError(String(status))
  e.response = {
    status,
    data: { detail },
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}

describe('进站 409 / 预检顶层 overridable（c6b5907）', () => {
  it('blockedOverridable 取 409 check_blocked 顶层字段，缺失为 null', () => {
    expect(
      blockedOverridable(
        ax(409, { code: 'check_blocked', overridable: false, results: [] })
      )
    ).toBe(false)
    expect(
      blockedOverridable(
        ax(409, { code: 'check_blocked', overridable: true, results: [] })
      )
    ).toBe(true)
    expect(
      blockedOverridable(ax(409, { code: 'check_blocked', results: [] }))
    ).toBeNull()
    expect(blockedOverridable(ax(409, { code: 'on_hold' }))).toBeNull()
    expect(blockedOverridable(new Error('x'))).toBeNull()
  })

  it('isHardBlock：顶层优先，缺失时按 results[] 兜底', () => {
    const soft = [r({})]
    const hard = [r({ overridable: false })]
    expect(isHardBlock(soft, false)).toBe(true)
    expect(isHardBlock(hard, true)).toBe(false)
    expect(isHardBlock(soft, null)).toBe(false)
    expect(isHardBlock(hard, undefined)).toBe(true)
  })

  it('顶层 false 时隐藏放行表单，true 时显示', async () => {
    const props = {
      results: [r({})],
      blocked: true,
      canOverride: true,
      onOverride: () => {},
    }
    const a = await render(<CheckPanel {...props} overridable={false} />)
    expect(a.container.querySelector('#override-reason')).toBeNull()
    a.unmount()
    const b = await render(<CheckPanel {...props} overridable />)
    await expect
      .element(b.getByLabelText(t('mes.exec.overrideReason')))
      .toBeVisible()
  })
})
