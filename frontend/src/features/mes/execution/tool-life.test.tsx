import i18n, { t } from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { CheckResult } from '@/lib/api/mes/execution'
import { checkMessage } from './check-message'
import { ToolLife } from './exec-actions'
import {
  maxUsage,
  toolLifeLevel,
  toolLifeMessage,
  toolLifeWarning,
  toolStatusText,
  warnRatio,
  withToolUsage,
} from './tool-life'

const chk = (p: Partial<CheckResult>): CheckResult => ({
  check_type: 'tool_life',
  rule_id: null,
  rule_code: null,
  rule_name: null,
  plan_code: null,
  severity: 'block',
  result: 'block',
  applicable: true,
  message: '',
  overridable: false,
  ...p,
})

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('F9 刀具寿命（B10 / D54-5）', () => {
  it('等级：上限 × warn_ratio 起为预警，>= 上限为到期；定点字符串不丢精度', () => {
    expect(toolLifeLevel('8.999999', '10.000000', 0.9)).toBe('ok')
    expect(toolLifeLevel('9', '10', 0.9)).toBe('warn')
    expect(toolLifeLevel('9.999999', '10.000000', 0.9)).toBe('warn')
    expect(toolLifeLevel('10.000000', '10', 0.9)).toBe('over')
    expect(toolLifeLevel('12', '10', 0.9)).toBe('over')
    expect(toolLifeLevel('5', null, 0.9)).toBeNull()
    expect(warnRatio({ warn_ratio: '0.800000', warn_pct: 90 })).toBe('0.8')
    expect(warnRatio({ warn_ratio: null, warn_pct: 95 })).toBe('0.95')
    expect(warnRatio({})).toBe('0.9')
  })

  it('寿命条按等级着色并去掉末尾零', async () => {
    const s = await render(
      <ToolLife
        row={{
          id: 'T1',
          usage_count: '95.500000',
          max_usage: '100.000000',
          warn_ratio: '0.9',
        }}
      />
    )
    const el = s.getByTestId('tool-life')
    await expect.element(el).toHaveAttribute('data-level', 'warn')
    await expect.element(el).toHaveTextContent('95.5/100')
    await expect.element(el).toHaveTextContent(t('mes.toolLife.warn'))
  })

  it('达到上限的 409 tool_life 不可放行，说明本地化', () => {
    const r = chk({ message: 'tool PC-01 reached its life (100.000000/100)' })
    expect(checkMessage(r)).toBe(
      t('mes.toolLife.reached', { tool: 'PC-01', used: '100', max: '100' })
    )
  })

  it('预警区间进站 200：提示接近上限并说明已记录；无预警为 null', () => {
    const w = chk({
      severity: 'warn',
      result: 'warn',
      overridable: true,
      message:
        'tool PC-01 near end of life (92.5/100); tool PC-01 expires on 2026-10-20',
    })
    expect(toolLifeMessage(w)).toBe(
      `${t('mes.toolLife.near', { tool: 'PC-01', used: '92.5', max: '100' })}；${t('mes.toolLife.expiring', { tool: 'PC-01', date: '2026-10-20' })}`
    )
    expect(toolLifeWarning([w])).toContain(t('mes.toolLife.logged'))
    expect(toolLifeWarning([chk({ result: 'pass', message: 'ok' })])).toBeNull()
  })

  it('23c502d：优先用 effective_max_usage / effective_warn_ratio，缺失或 null 回退旧逻辑', async () => {
    expect(
      warnRatio({ effective_warn_ratio: '0.750000', warn_ratio: '0.9' })
    ).toBe('0.75')
    expect(warnRatio({ effective_warn_ratio: null, warn_pct: 80 })).toBe('0.8')
    expect(
      maxUsage({ effective_max_usage: '500.000000', max_usage: null })
    ).toBe('500')
    expect(maxUsage({ effective_max_usage: null, max_usage: '20' })).toBe('20')
    expect(maxUsage({})).toBeNull()
    // 工具自身没有上限、沿用类型上限：仍按有效值着色
    const s = await render(
      <ToolLife
        row={{
          id: 'T2',
          usage_count: '380.000000',
          max_usage: null,
          effective_max_usage: '500.000000',
          effective_warn_ratio: '0.750000',
        }}
      />
    )
    const el = s.getByTestId('tool-life')
    await expect.element(el).toHaveAttribute('data-level', 'warn')
    await expect.element(el).toHaveTextContent('380/500')
  })

  it('进站上下文 options[].warn_ratio（字符串）优先于 warn_pct', () => {
    const o = { warn_pct: 90, warn_ratio: '0.5' }
    expect(toolLifeLevel('6', '10', warnRatio(o))).toBe('warn')
    expect(toolLifeLevel('6', '10', warnRatio({ warn_pct: 90 }))).toBe('ok')
  })

  it('P2-D4：用量 >= 上限时即使后端给状态类说明，也显示已达寿命上限（用量/上限）', () => {
    const r = chk({
      message: 'tool PC-01 is pending_maintenance',
      data: { tool_id: 'T1', tool: 'PC-01' },
    })
    const cx = {
      tools: [
        {
          fixture: null,
          options: [
            {
              id: 'T1',
              code: 'PC-01',
              status: 'pending_maintenance',
              usage: '10.000000',
              max: '10',
              expiry: null,
              warn_pct: 90,
            },
          ],
        },
      ],
    }
    const [x] = withToolUsage([r], cx as never)
    expect(checkMessage(x)).toBe(
      t('mes.toolLife.reached', { tool: 'PC-01', used: '10', max: '10' })
    )
    // 没拿到用量：状态走三语翻译
    expect(checkMessage(r)).toBe(
      t('mes.toolLife.status', { tool: 'PC-01', status: '待保养' })
    )
    expect(checkMessage(r)).not.toMatch(/pending_maintenance/)
  })

  it('未登记的工具状态码不原样显示（三语）', async () => {
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      expect(toolStatusText('pending_maintenance')).not.toBe(
        'pending_maintenance'
      )
      const m = checkMessage(chk({ message: 'tool PC-01 is frozen_xyz' }))
      expect(m).not.toMatch(/frozen_xyz/)
      expect(m).toContain(t('mes.toolLife.unknownStatus'))
    }
    await i18n.changeLanguage('zh-CN')
  })
})
