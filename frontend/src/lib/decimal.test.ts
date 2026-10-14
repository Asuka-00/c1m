import { describe, expect, it } from 'vitest'
import { decimalGreater, decimalText, parseDecimal } from './decimal'

describe('parseDecimal（D49）', () => {
  it('去掉末尾零再数位数', () => {
    expect(parseDecimal('1.5000000')).toEqual({
      text: '1.5',
      negative: false,
      decimals: 1,
    })
    expect(parseDecimal('010.00')?.text).toBe('10')
    expect(parseDecimal('.25')?.decimals).toBe(2)
  })
  it('科学计数法按换算后的十进制位数', () => {
    expect(parseDecimal('1e-7')).toEqual({
      text: '0.0000001',
      negative: false,
      decimals: 7,
    })
    expect(parseDecimal('1.5E-3')?.text).toBe('0.0015')
    expect(parseDecimal('1.25e2')).toMatchObject({ text: '125', decimals: 0 })
  })
  it('负数与非数字', () => {
    expect(parseDecimal('-0.5')).toMatchObject({ text: '-0.5', negative: true })
    expect(parseDecimal('-0')?.negative).toBe(false)
    for (const bad of ['abc', '1.2.3', '', '1e', 'NaN', 'Infinity', '1,5'])
      expect(parseDecimal(bad)).toBeNull()
  })
  it('接口数字显示不丢精度、不出指数', () => {
    expect(decimalText(0.000125)).toBe('0.000125')
    expect(decimalText(1e-7)).toBe('0.0000001')
    expect(decimalText(123456.123456)).toBe('123456.123456')
    expect(decimalText(1.5e21)).toBe('1500000000000000000000')
    expect(decimalText(null)).toBe('')
  })
  it('decimalGreater', () => {
    expect(decimalGreater('1.0001', '1')).toBe(true)
    expect(decimalGreater('1', '1')).toBe(false)
    expect(decimalGreater('0.9999', '1')).toBe(false)
    expect(decimalGreater('10', '9')).toBe(true)
  })
})
