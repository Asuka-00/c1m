/**
 * 十进制字符串工具（D49）：全程按字符串处理，不经过浮点运算，不丢精度。
 * 支持正负号、前导点（".5"）和科学计数法（"1.5e-3"）。
 */

export interface Decimal {
  /** 规范化后的字符串：无指数、无前导零、无末尾零，例如 "-0.0015"、"12" */
  text: string
  negative: boolean
  /** 去掉末尾零后的小数位数 */
  decimals: number
}

const RE = /^([+-]?)(\d+\.?\d*|\.\d+)(?:e([+-]?\d+))?$/i

/** 解析十进制字符串；不是数字返回 null。 */
export function parseDecimal(input: string): Decimal | null {
  const m = RE.exec(input.trim())
  if (!m) return null
  const [, sign, mant, exp] = m
  const dot = mant.indexOf('.')
  let digits = mant.replace('.', '')
  // 小数点位置（整数部分长度），再按指数移动
  let point = (dot < 0 ? mant.length : dot) + (exp ? Number(exp) : 0)
  if (!Number.isFinite(point) || Math.abs(point) > 1000) return null
  if (point < 0) {
    digits = '0'.repeat(-point) + digits
    point = 0
  } else if (point > digits.length) {
    digits = digits + '0'.repeat(point - digits.length)
  }
  const int = digits.slice(0, point).replace(/^0+/, '') || '0'
  const frac = digits.slice(point).replace(/0+$/, '')
  const zero = int === '0' && frac === ''
  const negative = sign === '-' && !zero
  const text = `${negative ? '-' : ''}${int}${frac ? `.${frac}` : ''}`
  return { text, negative, decimals: frac.length }
}

/** 接口返回的数字转成完整的十进制文本（不出现 "1e-7" 这类指数写法）。 */
export function decimalText(v: number | string | null | undefined): string {
  if (v == null || v === '') return ''
  return parseDecimal(String(v))?.text ?? String(v)
}

/** 比较两个规范化后的非负十进制文本：a > b 返回 true。 */
export function decimalGreater(a: string, b: string): boolean {
  const [ai, af = ''] = a.split('.')
  const [bi, bf = ''] = b.split('.')
  if (ai.length !== bi.length) return ai.length > bi.length
  if (ai !== bi) return ai > bi
  const n = Math.max(af.length, bf.length)
  return af.padEnd(n, '0') > bf.padEnd(n, '0')
}
