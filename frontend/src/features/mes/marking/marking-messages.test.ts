import i18n, { t } from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import type { CheckResult } from '@/lib/api/mes/execution'
import { apiError } from '@/lib/api/mes/reticle'
import {
  checkMessage,
  markingCheckInfo,
} from '@/features/mes/execution/check-message'
import { markingErrorMessage } from './marking-rules'

const chk = (data: Record<string, unknown>): CheckResult =>
  ({
    check_type: 'marking_inspection',
    result: 'block',
    overridable: false,
    message: 'blocked',
    data,
  }) as unknown as CheckResult

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('出站 check_blocked marking_inspection 文案（D79 补充）', () => {
  it('尚未打标', () => {
    expect(checkMessage(chk({ reason: 'not_marked' }))).toBe(
      t('mes.marking.checkNotMarked')
    )
    expect(checkMessage(chk({}))).toBe(t('mes.marking.checkNotMarked'))
  })
  it('待检验 / 不合格', () => {
    expect(checkMessage(chk({ trace_code: 'A1', reason: 'pending' }))).toBe(
      t('mes.marking.checkPending', { trace: 'A1' })
    )
    expect(checkMessage(chk({ trace_code: 'A1', reason: 'fail' }))).toBe(
      t('mes.marking.checkBlocked', { trace: 'A1' })
    )
  })
})

describe('ctx.reason（D79 补充）', () => {
  const ctx = (c: Record<string, unknown>) =>
    ({
      check_type: 'marking_inspection',
      result: 'block',
      overridable: false,
      message: 'x',
      ctx: c,
    }) as unknown as CheckResult
  it('not_marked / pending / fail 分别显示，marking_id 可取', () => {
    expect(checkMessage(ctx({ reason: 'not_marked' }))).toBe(
      t('mes.marking.checkNotMarked')
    )
    expect(
      checkMessage(
        ctx({ reason: 'pending', marking_id: 'm1', trace_code: 'A1' })
      )
    ).toBe(t('mes.marking.checkPending', { trace: 'A1' }))
    expect(
      checkMessage(ctx({ reason: 'fail', marking_id: 'm1', trace_code: 'A1' }))
    ).toBe(t('mes.marking.checkBlocked', { trace: 'A1' }))
    expect(
      markingCheckInfo(ctx({ reason: 'fail', marking_id: 'm1' })).markingId
    ).toBe('m1')
  })
})

describe('打标错误文案', () => {
  it.each(['zh-CN', 'en', 'ja'])('%s：no_active_marking 有文案', async (l) => {
    await i18n.changeLanguage(l)
    const msg = markingErrorMessage(
      apiError(409, { code: 'no_active_marking', message: 'x' })
    )
    expect(msg).toBe(t('mes.marking.code.no_active_marking'))
    expect(msg).not.toContain('mes.marking')
  })
  it('自批 422 ctx.reason=self_approval', () => {
    expect(
      markingErrorMessage(
        apiError(422, [
          {
            loc: ['body', 'approved_by'],
            type: 'value_error',
            ctx: { reason: 'self_approval' },
          },
        ])
      )
    ).toBe(t('mes.marking.err.selfApproval'))
  })
})

describe('D79 补充四：超长 / 格式错误文案', () => {
  const e = (loc: string, ctx: Record<string, unknown>) =>
    apiError(422, [{ loc: ['body', loc], type: 'value_error', ctx }])
  it('trace_code 超长用 ctx.max_length', () => {
    expect(
      markingErrorMessage(
        e('trace_code', { reason: 'max_length', max_length: 20 })
      )
    ).toBe(t('mes.marking.err.trace_max_length', { n: 20 }))
  })
  it('read_code 超长用读回码文案和 ctx.max_length', () => {
    expect(
      markingErrorMessage(
        e('read_code', { reason: 'max_length', max_length: 128 })
      )
    ).toBe(t('mes.marking.err.readCodeTooLong', { n: 128 }))
  })
  it('格式错误：默认正则用固定文案，自定义正则显示原样正则', () => {
    expect(
      markingErrorMessage(
        e('trace_code', { reason: 'pattern', pattern: '^[A-Z0-9-]+$' })
      )
    ).toBe(t('mes.marking.err.trace_pattern', { n: 32 }))
    expect(
      markingErrorMessage(
        e('trace_code', { reason: 'pattern', pattern: '^[A-F0-9]+$' })
      )
    ).toBe(t('mes.marking.err.trace_pattern_rule', { pattern: '^[A-F0-9]+$' }))
  })
})
