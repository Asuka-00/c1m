import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { MesEntity } from '@/lib/api/mes/common'
import { mesErrorMessage, validateDecimals } from './required'

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
    { name: 'max_usage', column: 'max_usage', type: 'float' },
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
