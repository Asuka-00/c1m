import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { MesEntity } from '@/lib/api/mes/common'
import { decimalLimit, mesErrorMessage, validateDecimals } from './required'

function axErr(status: number, detail: unknown) {
  const e = new AxiosError('Request failed')
  e.response = {
    status,
    data: { detail },
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}

const toolE = {
  code: 'tool',
  fields: [
    {
      name: 'max_usage',
      column: 'max_usage',
      type: 'float',
      scale: 6,
      decimal_places: 6,
    },
    { name: 'lsl', column: 'lsl', type: 'float', decimal_places: null },
    { name: 'rate', column: 'rate', type: 'float', decimal_places: 3 },
    { name: 'warn_pct', column: 'warn_pct', type: 'int' },
  ],
} as unknown as MesEntity

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('D60 定点数最多 6 位小数', () => {
  it('表单提交前校验：超过 6 位提示，6 位以内通过', () => {
    expect(
      validateDecimals(toolE, { max_usage: '1.1234567' }, new Set())
    ).toEqual({
      max_usage: '最多 6 位小数',
    })
    expect(
      validateDecimals(toolE, { max_usage: '1.123456' }, new Set())
    ).toEqual({})
    expect(
      validateDecimals(toolE, { max_usage: '1.1000000' }, new Set())
    ).toEqual({})
    expect(validateDecimals(toolE, { max_usage: '' }, new Set())).toEqual({})
  })

  it('422 too_many_decimals 三语（数组与 detail.code 两种形态）', async () => {
    const arr = axErr(422, [
      {
        loc: ['body', 'max_usage'],
        msg: 'max_usage: at most 6 decimal places',
        type: 'too_many_decimals',
      },
    ])
    for (const [lng, want] of [
      ['zh-CN', '最多 6 位小数'],
      ['en', 'At most 6 decimal places'],
      ['ja', '小数は最大 6 桁です'],
    ]) {
      await i18n.changeLanguage(lng)
      expect(mesErrorMessage(arr, undefined)).toBe(want)
      expect(
        mesErrorMessage(axErr(422, { code: 'too_many_decimals' }), undefined)
      ).toBe(want)
    }
    await i18n.changeLanguage('zh-CN')
    expect(mesErrorMessage(arr, toolE)).toContain(
      t('mes.err.tooManyDecimals', { n: 6 })
    )
    expect(mesErrorMessage(arr, toolE)).not.toMatch(/decimal places/)
  })
})

describe('D60 decimal_places（0dd2b4b）', () => {
  it('普通浮点 decimal_places=null 不限位数', () => {
    expect(
      validateDecimals(toolE, { lsl: '0.000000012345' }, new Set())
    ).toEqual({})
  })
  it('按 decimal_places 限位，先去掉末尾 0 再数', () => {
    expect(validateDecimals(toolE, { rate: '1.2340000' }, new Set())).toEqual(
      {}
    )
    expect(validateDecimals(toolE, { rate: '1.2345' }, new Set())).toEqual({
      rate: '最多 3 位小数',
    })
  })
  it('decimalLimit：decimal_places 优先，旧元数据退回 scale', () => {
    const f = (x: object) =>
      ({ name: 'x', column: 'x', type: 'float', ...x }) as never
    expect(decimalLimit(f({ decimal_places: 4, scale: 6 }))).toBe(4)
    expect(decimalLimit(f({ decimal_places: null, scale: 6 }))).toBeNull()
    expect(decimalLimit(f({ scale: 2 }))).toBe(2)
    expect(decimalLimit(f({}))).toBeNull()
  })
})
