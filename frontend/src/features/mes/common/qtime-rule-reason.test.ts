import { AxiosError, AxiosHeaders } from 'axios'
import { t } from '@/i18n'
import { describe, expect, it } from 'vitest'
import type { MesEntity, MesField } from '@/lib/api/mes/common'
import { overrideEnumOptions } from './fe-overrides'
import { enumLabel, fieldHelp } from './labels'
import {
  mesErrorMessage,
  requiredBy,
  requiredHint,
  validateRequired,
} from './required'

const f = (x: Partial<MesField>) =>
  ({ required: false, required_when: null, help: null, ...x }) as MesField
const action = f({
  name: 'action',
  column: 'action',
  type: 'enum',
  enum: 'qtime_action',
  required: true,
})
// 后端元数据（ecc6ca5）仍带 required_when；D25 起前端视为可选
const reason = f({
  name: 'reason',
  column: 'reason_id',
  type: 'ref',
  ref: 'reason_code',
  required_when: { action: ['hold', 'scrap'] },
})
const ent = (code: string) =>
  ({ code, fields: [action, reason] }) as unknown as MesEntity

describe('D26：Q-Time 规则动作只有 hold / rework', () => {
  const all = ['warn', 'hold', 'rework', 'scrap']
  it('表单下拉只有 hold / rework', () => {
    expect(overrideEnumOptions('qtime_action', all, 'hold')).toEqual([
      'hold',
      'rework',
    ])
    expect(
      overrideEnumOptions('qtime_action', ['hold', 'rework', 'scrap'])
    ).toEqual(['hold', 'rework'])
  })
  it('旧数据 action=scrap 仍保留选项并显示标签', () => {
    expect(overrideEnumOptions('qtime_action', all, 'scrap')).toContain('scrap')
    expect(enumLabel('qtime_action', 'scrap')).not.toBe('scrap')
  })
  it('其他枚举不受影响', () => {
    expect(overrideEnumOptions('lot_disposition', ['scrap', 'hold'])).toEqual([
      'scrap',
      'hold',
    ])
  })
  it('422 qtime_action_invalid 按 code 本地化', () => {
    const e = new AxiosError('Request failed')
    e.response = {
      status: 422,
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
      data: { detail: { code: 'qtime_action_invalid', message: 'bad action' } },
    }
    expect(mesErrorMessage(e, ent('qtime_rule'))).toBe(
      t('mes.err.code.qtime_action_invalid')
    )
  })
})

describe('D25：Q-Time 规则原因码可空', () => {
  it('action=hold 时原因码不必填，前端不拦截提交', () => {
    const v = { action: 'hold', reason_id: null }
    expect(requiredBy(ent('qtime_rule'), reason, v)).toBeNull()
    expect(requiredHint(ent('qtime_rule'), reason, v)).toBe('')
    expect(validateRequired(ent('qtime_rule'), v, new Set())).toEqual({})
  })

  it('覆盖不修改字段元数据本身（即使旧数据 action=scrap 也不拦截）', () => {
    expect(
      validateRequired(ent('qtime_rule'), { action: 'scrap' }, new Set())
    ).toEqual({})
    requiredBy(ent('qtime_rule'), reason, { action: 'hold' })
    expect(reason.required_when).toEqual({ action: ['hold', 'scrap'] })
  })

  it('其他实体的 required_when 不受影响', () => {
    const v = { action: 'hold', reason_id: null }
    expect(requiredBy(ent('other'), reason, v)).not.toBeNull()
    expect(requiredHint(ent('other'), reason, v)).not.toBe('')
    expect(validateRequired(ent('other'), v, new Set()).reason).toBeTruthy()
  })

  it('原因码字段显示「留空使用 qtime_expired」提示', () => {
    expect(fieldHelp(ent('qtime_rule'), reason)).toBe(
      t('mes.qtimeRule.reasonHint')
    )
    expect(t('mes.qtimeRule.reasonHint')).toContain('qtime_expired')
    expect(fieldHelp(ent('other'), reason)).toBe('')
  })

  it('填写了不存在 / 他租户的原因码时，照常显示后端 422', () => {
    const e = new AxiosError('Request failed')
    e.response = {
      status: 422,
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
      data: {
        detail: [
          {
            loc: ['body', 'reason_id'],
            msg: 'reason: not found',
            type: 'value_error',
          },
        ],
      },
    }
    const msg = mesErrorMessage(e, ent('qtime_rule'))
    expect(msg).toBeTruthy()
    expect(msg).not.toBe(t('mes.qtimeRule.reasonHint'))
  })
})
