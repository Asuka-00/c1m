import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { MesEntity } from '@/lib/api/mes/common'
import {
  mesErrorMessage,
  validateRequired,
} from '@/features/mes/common/required'
import { undoErrorLines } from '@/features/mes/execution/transform-undo'
import {
  alarmStateNote,
  alarmStateOf,
  SKIP_REASON_CODES,
  skipReasonText,
} from './alarm-state'

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

const ent = {
  code: 'alarm_code',
  fields: [
    {
      name: 'action',
      column: 'action',
      type: 'enum',
      enum: 'alarm_action',
      required: true,
      required_when: null,
    },
    {
      name: 'target_state',
      column: 'target_state',
      type: 'str',
      required: false,
      required_when: null,
    },
  ],
} as unknown as MesEntity

const ax = (status: number, data: unknown) => {
  const e = new AxiosError(String(status))
  e.response = {
    status,
    data,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}

describe('D59 报警码联动 none / set_state + target_state', () => {
  it('set_state 时 target_state 必填；none 时不能填；none 空值通过', () => {
    expect(
      validateRequired(
        ent,
        { action: 'set_state', target_state: '' },
        new Set()
      ).target_state
    ).toBeTruthy()
    expect(
      validateRequired(
        ent,
        { action: 'set_state', target_state: 'UDT' },
        new Set()
      )
    ).toEqual({})
    expect(
      validateRequired(ent, { action: 'none', target_state: 'UDT' }, new Set())
        .target_state
    ).toContain('切换设备状态')
    expect(validateRequired(ent, { action: 'none' }, new Set())).toEqual({})
  })

  it('后端 422 target_state 三条消息本地化', async () => {
    const m = (msg: string) =>
      mesErrorMessage(
        ax(422, { detail: [{ loc: ['body', 'target_state'], msg }] }),
        ent
      )
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      expect(m('target_state: required when action=set_state')).toContain(
        t('mes.alarm.err.targetRequired')
      )
      expect(m('target_state: only allowed when action=set_state')).toContain(
        t('mes.alarm.err.targetOnly')
      )
      expect(m('target_state: unknown E10 state NOPE')).toContain('NOPE')
      expect(m('target_state: unknown E10 state NOPE')).not.toContain(
        'unknown E10'
      )
    }
  })
})

describe('state_skip_reason 错误码（baf7b55）', () => {
  it('三个码三语翻译，未知码原样，不再按英文句式解析', async () => {
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      for (const c of SKIP_REASON_CODES) {
        expect(i18n.exists(`mes.alarm.skip.${c}`)).toBe(true)
        expect(skipReasonText(c)).toBe(t(`mes.alarm.skip.${c}`))
        expect(skipReasonText(c)).not.toBe(c)
      }
    }
    expect(skipReasonText('weird_code')).toBe('weird_code')
    expect(skipReasonText('already DOWN')).toBe('already DOWN')
    expect(skipReasonText(null)).toBe('')
    expect(i18n.exists('mes.alarm.skip.notAllowed')).toBe(false)
  })

  it('仅 state_changed=false 时有说明', () => {
    expect(alarmStateNote({ state_changed: true })).toBeNull()
    expect(alarmStateNote(null)).toBeNull()
    expect(
      alarmStateNote({
        state_changed: false,
        state_skip_reason: 'already_in_state',
      })
    ).toBe('设备状态未切换：设备已处于目标状态。报警已记录。')
    expect(alarmStateNote({ state_changed: false })).toBe(
      t('mes.alarm.stateUnchanged')
    )
  })

  it('履历行：顶层字段优先，退回 e10_change', () => {
    expect(
      alarmStateOf({ state_changed: false, state_skip_reason: 'unknown_state' })
    ).toEqual({ state_changed: false, state_skip_reason: 'unknown_state' })
    expect(
      alarmStateOf({
        e10_change: {
          state_changed: false,
          state_skip_reason: 'transition_not_allowed',
        },
      })
    ).toEqual({
      state_changed: false,
      state_skip_reason: 'transition_not_allowed',
    })
    expect(alarmStateOf({}).state_changed).toBeUndefined()
  })
})

describe('B6 409 reason（752503e）', () => {
  it('already_undone / lots_blocked（含 referenced）', () => {
    expect(
      undoErrorLines(
        ax(409, {
          detail: {
            code: 'transform_undo_blocked',
            reason: 'already_undone',
            lots: [],
          },
        })
      )
    ).toEqual([t('mes.tundo.already')])
    const l = undoErrorLines(
      ax(409, {
        detail: {
          code: 'transform_undo_blocked',
          reason: 'lots_blocked',
          lots: [{ lot_code: 'L1-001', reason: 'referenced' }],
        },
      })
    )
    expect(l[0]).toContain('L1-001')
    expect(l[0]).toContain(t('mes.tundo.why.referenced'))
  })
})
