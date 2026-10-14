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

type DecIn = number | string | null | undefined

/** 转成 [整数 BigInt, 小数位]；不是数字返回 null。兼容 number（mock / 旧接口）。 */
function toScaled(v: DecIn): [bigint, number] | null {
  if (v == null || v === '') return null
  const d = parseDecimal(String(v))
  if (!d) return null
  return [BigInt(d.text.replace('.', '')), d.decimals]
}

const pow10 = (n: number) => 10n ** BigInt(n)

/**
 * 按十进制比较两个值（D72：定点字符串，兼容 number）：a < b 为 -1，相等 0，a > b 为 1。
 * 不是数字的值排在最后（两个都不是数字为 0）。
 */
export function compareDecimal(a: DecIn, b: DecIn): -1 | 0 | 1 {
  const x = toScaled(a)
  const y = toScaled(b)
  if (!x || !y) return x ? -1 : y ? 1 : 0
  const s = Math.max(x[1], y[1])
  const p = x[0] * pow10(s - x[1])
  const q = y[0] * pow10(s - y[1])
  return p < q ? -1 : p > q ? 1 : 0
}

/** 精确加法（不经过浮点）；任一不是数字时返回 null。 */
export function addDecimal(a: DecIn, b: DecIn): string | null {
  const x = toScaled(a)
  const y = toScaled(b)
  if (!x || !y) return null
  const s = Math.max(x[1], y[1])
  const sum = x[0] * pow10(s - x[1]) + y[0] * pow10(s - y[1])
  const neg = sum < 0n
  const digits = (neg ? -sum : sum).toString().padStart(s + 1, '0')
  const raw = s
    ? `${digits.slice(0, digits.length - s)}.${digits.slice(digits.length - s)}`
    : digits
  return parseDecimal(`${neg ? '-' : ''}${raw}`)!.text
}

/** 是否为可解析的十进制值（字符串或有限数字）。 */
export const isDecimal = (v: unknown): v is number | string =>
  (typeof v === 'number' && Number.isFinite(v)) ||
  (typeof v === 'string' && parseDecimal(v) != null)
