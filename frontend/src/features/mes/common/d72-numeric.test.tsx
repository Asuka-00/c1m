/** D72：通用 CRUD numeric 列定点字符串输出、422 value_error ctx.max_places、409 referenced。 */
import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { errorMessage } from '@/lib/api/client'
import type { MesEntity } from '@/lib/api/mes/common'
import {
  addDecimal,
  compareDecimal,
  decimalText,
  isDecimal,
} from '@/lib/decimal'
import { bomError } from '@/features/mes/product/bom-errors'
import { cellValue } from './cells'
import { toPayload } from './form-payload'
import { mesCodeMessage, mesErrorMessage } from './required'

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

const lotE = {
  code: 'material_lot',
  fields: [
    { name: 'qty_remaining', column: 'qty_remaining', type: 'float', scale: 6 },
    { name: 'warn_ratio', column: 'warn_ratio', type: 'float', scale: 4 },
    { name: 'lsl', column: 'lsl', type: 'float', scale: null },
  ],
} as unknown as MesEntity

const valueErr = (field: string, n: number) => ({
  loc: ['body', field],
  msg: `${field}: Value error, at most ${n} decimal places`,
  type: 'value_error',
  code: 'value_error',
  ctx: { max_places: n },
})

afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('lib/decimal：比较与加法（不经过浮点）', () => {
  it('compareDecimal 字符串 / 数字混用', () => {
    expect(compareDecimal('0.3', 0.3)).toBe(0)
    expect(compareDecimal('100000.000000', '100000')).toBe(0)
    expect(compareDecimal('99999.999999', 100000)).toBe(-1)
    expect(compareDecimal('-1', '-0.5')).toBe(-1)
    expect(compareDecimal('123456789012.000001', '123456789012')).toBe(1)
    expect(compareDecimal('x', '1')).toBe(1)
    expect(compareDecimal(null, null)).toBe(0)
  })
  it('addDecimal 精确', () => {
    expect(addDecimal('0.1', '0.2')).toBe('0.3')
    expect(addDecimal('45000', '-0.000001')).toBe('44999.999999')
    expect(addDecimal('1', '-1')).toBe('0')
    expect(addDecimal('-0.5', 0.25)).toBe('-0.25')
    expect(addDecimal('123456789012.5', '0.5')).toBe('123456789013')
    expect(addDecimal('a', 1)).toBeNull()
  })
  it('isDecimal', () => {
    expect(isDecimal('1.500000')).toBe(true)
    expect(isDecimal(2)).toBe(true)
    expect(isDecimal('abc')).toBe(false)
    expect(isDecimal(NaN)).toBe(false)
  })
})

describe('通用 CRUD numeric 列（定点字符串，兼容数字）', () => {
  it('列表 / 详情单元格按十进制显示，不出现指数', async () => {
    const cases: [unknown, string][] = [
      ['12.500000', '12.5'],
      [1e-7, '0.0000001'],
      ['0', '0'],
    ]
    for (const [v, want] of cases) {
      const s = await render(
        <div>
          {cellValue(lotE, { id: '1', qty_remaining: v }, 'qty_remaining')}
        </div>
      )
      expect(s.container.textContent).toBe(want)
      await s.unmount()
    }
  })
  it('提交体：定点字段为十进制字符串，普通浮点仍为数字', () => {
    const out = toPayload(
      lotE,
      {
        qty_remaining: '123456789012.123456',
        warn_ratio: '0.9000',
        lsl: '1.5',
      },
      new Set()
    )
    expect(out.qty_remaining).toBe('123456789012.123456')
    expect(out.warn_ratio).toBe('0.9')
    expect(out.lsl).toBe(1.5)
    expect(
      toPayload(lotE, { qty_remaining: '' }, new Set()).qty_remaining
    ).toBeNull()
  })
})

describe('422 value_error + ctx.max_places（D72）', () => {
  it('通用实体：按 ctx.max_places 提示位数（三语）', async () => {
    const e = axErr(422, [valueErr('warn_ratio', 4)])
    expect(mesErrorMessage(e, lotE)).toContain(
      t('mes.err.tooManyDecimals', { n: 4 })
    )
    for (const lng of ['en', 'ja', 'zh-CN']) {
      await i18n.changeLanguage(lng)
      const m = errorMessage(axErr(422, [valueErr('qty', 6)]))
      expect(m).toBe(t('mes.err.tooManyDecimals', { n: 6 }))
      expect(m).toContain('6')
    }
  })
  it('没有 ctx 的 value_error 不当成小数位错误', () => {
    const e = axErr(422, [
      {
        loc: ['body', 'qty_remaining'],
        msg: 'qty_remaining: must be a number',
        type: 'value_error',
      },
    ])
    expect(mesErrorMessage(e, lotE)).not.toContain(
      t('mes.err.tooManyDecimals', { n: 6 })
    )
  })
  it('BOM：scrap_rate 4 位、qty 6 位取自 ctx', () => {
    const r = bomError(
      axErr(422, [
        { ...valueErr('qty', 6), loc: ['body', 'lines', 0, 'qty'] },
        {
          ...valueErr('scrap_rate', 4),
          loc: ['body', 'lines', 1, 'scrap_rate'],
        },
      ])
    )
    expect(r.fields).toEqual([
      {
        line: 0,
        field: 'qty',
        message: t('mes.bomTab.err.tooManyDecimals', { n: 6 }),
      },
      {
        line: 1,
        field: 'scrap_rate',
        message: t('mes.bomTab.err.tooManyDecimals', { n: 4 }),
      },
    ])
  })
})

describe('409 referenced（D72）', () => {
  it('对象形式 referenced 走三语文案，不露英文 message', () => {
    const m = mesCodeMessage(
      axErr(409, {
        code: 'referenced',
        message: 'reticle R1 has history; scrap it instead',
        tables: ['mes_reticle_usage'],
      })
    )
    expect(m).toBe(t('mes.err.code.referenced'))
  })
  it('其他实体的 409 文本仍按原文本翻译', () => {
    const m = mesErrorMessage(
      axErr(409, 'Record is referenced by other records'),
      undefined
    )
    expect(m).toBe(t('backend.Record is referenced by other records'))
  })
})

it('decimalText 仍兼容数字', () => {
  expect(decimalText(100000)).toBe('100000')
})
