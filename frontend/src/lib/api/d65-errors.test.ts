import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { MesEntity } from '@/lib/api/mes/common'
import { permDesc, permLabel, roleDesc } from '@/lib/rbac-labels'
import { mesErrorMessage } from '@/features/mes/common/required'
import { alarmStateOf } from '@/features/mes/equipment/alarm-state'
import { errorMessage } from './client'

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
const ent = {
  code: 'alarm_code',
  fields: [{ name: 'alid', column: 'alid', type: 'str' }],
} as unknown as MesEntity

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('D65 查询参数 422：列表与旧字符串双兼容', () => {
  const sortMsg = 'sort_by must be one of: code, created_at'
  it.each(['zh-CN', 'en', 'ja'])('%s sort_by', async (lng) => {
    await i18n.changeLanguage(lng)
    const want = t('errors.query.sortBy', { list: 'code, created_at' })
    const list = ax(422, [{ loc: ['query', 'sort_by'], msg: sortMsg }])
    const str = ax(422, sortMsg)
    for (const e of [list, str]) {
      expect(errorMessage(e)).toBe(want)
      expect(mesErrorMessage(e, ent)).toBe(want)
    }
  })

  it('不是文本筛选字段', () => {
    const msg = 'foo is not a text filter'
    const want = t('errors.query.notTextFilter', { field: 'foo' })
    expect(errorMessage(ax(422, [{ loc: ['query', 'field'], msg }]))).toBe(want)
    expect(errorMessage(ax(422, msg))).toBe(want)
    expect(mesErrorMessage(ax(422, msg), ent)).toBe(want)
  })

  it('其他查询参数错误：参数名前缀，不映射表单字段', () => {
    const e = ax(422, [
      {
        loc: ['query', 'alid'],
        msg: 'alid: invalid date',
        type: 'value_error',
      },
    ])
    expect(mesErrorMessage(e, ent)).toBe('alid: invalid date')
    expect(errorMessage(e)).toBe('alid: invalid date')
  })

  it('列表项带固定码按码取文案（mes.err.code.*）', () => {
    const e = ax(422, [
      {
        loc: ['query', 'date_to'],
        msg: 'x',
        type: 'too_many_decimals',
        code: 'too_many_decimals',
      },
    ])
    expect(errorMessage(e)).toBe(t('mes.err.code.too_many_decimals'))
  })
})

describe('D65 unknown_field 映射', () => {
  it('{loc:[body,foo], type/code: unknown_field}', async () => {
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      const m = mesErrorMessage(
        ax(422, [
          {
            loc: ['body', 'foo'],
            msg: 'foo: unknown field',
            type: 'unknown_field',
            code: 'unknown_field',
          },
        ]),
        ent
      )
      expect(m).toBe(t('mes.err.unknownField'))
      expect(m).not.toContain('unknown field')
    }
  })
})

describe('D65 报警履历顶层 state_changed 优先', () => {
  it('顶层与 e10_change 都有时用顶层', () => {
    expect(
      alarmStateOf({
        state_changed: true,
        state_skip_reason: null,
        e10_change: {
          state_changed: false,
          state_skip_reason: 'unknown_state',
        },
      })
    ).toEqual({ state_changed: true, state_skip_reason: null })
  })
})

describe('mes.eap:read_master 三语', () => {
  it.each(['zh-CN', 'en', 'ja'])('%s', async (lng) => {
    await i18n.changeLanguage(lng)
    for (const c of ['mes.eap:read_master', 'mes.eap:write']) {
      expect(
        i18n.exists(`permName.${c.replace('.', '_').replace(':', '__')}`)
      ).toBe(true)
      expect(permLabel(c, null)).not.toBe(c)
      expect(permDesc(c, null)).toBeTruthy()
    }
    expect(
      roleDesc({ name: 'eap_service', description: null }, false)
    ).toBeTruthy()
  })
  it('数据库内置英文名会翻成当前语言', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(
      permLabel('mes.eap:read_master', 'EAP master data read (service account)')
    ).toBe('EAP 主数据只读（服务账号）')
  })
})

describe('D65 补充 2', () => {
  it('path 类 loc 与 query 一样不映射表单字段', () => {
    const e = ax(422, [
      {
        loc: ['path', 'alid'],
        msg: 'alid: invalid uuid',
        type: 'value_error',
        code: 'value_error',
      },
    ])
    expect(mesErrorMessage(e, ent)).toBe('alid: invalid uuid')
    expect(mesErrorMessage(e, ent)).not.toContain(':  ')
  })

  it('先 code 再 type', () => {
    const e = ax(422, [
      {
        loc: ['body', 'set_at'],
        msg: 'x',
        type: 'value_error',
        code: 'timezone_required',
      },
    ])
    expect(errorMessage(e)).toBe(t('mes.err.code.timezone_required'))
    const typeOnly = ax(422, [
      { loc: ['body', 'set_at'], msg: 'x', type: 'timezone_required' },
    ])
    expect(errorMessage(typeOnly)).toBe(t('mes.err.code.timezone_required'))
  })

  it.each(['zh-CN', 'en', 'ja'])('%s timezone_required 文案', async (lng) => {
    await i18n.changeLanguage(lng)
    expect(i18n.exists('mes.err.code.timezone_required')).toBe(true)
    const m = mesErrorMessage(
      ax(422, [
        {
          loc: ['body', 'set_at'],
          msg: 'set_at: timezone required',
          type: 'timezone_required',
          code: 'timezone_required',
        },
      ]),
      ent
    )
    expect(m).toBe(t('mes.err.code.timezone_required'))
  })
})
