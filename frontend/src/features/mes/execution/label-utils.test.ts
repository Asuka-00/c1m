import { describe, expect, it } from 'vitest'
import { barcodeSvg, labelHtml, printHtml, qrSvg } from './label-utils'

describe('label-utils', () => {
  it('生成条码与二维码 SVG', async () => {
    expect(barcodeSvg('DM26100002')).toContain('<svg')
    expect(await qrSvg('DM26100002')).toContain('<svg')
  })
  it('标签 HTML 转义文本并标记急件', async () => {
    const h = await labelHtml(
      { code: 'L1', title: '<b>x</b>', lines: ['a&b'], hot: true },
      'qr'
    )
    expect(h).toContain('&lt;b&gt;x&lt;/b&gt;')
    expect(h).toContain('a&amp;b')
    expect(h).toContain('label hot')
    expect(h).not.toContain('class="bar"')
  })
  it('打印页面包含全部标签', async () => {
    const h = await printHtml(
      [
        { code: 'A', title: 't', lines: [] },
        { code: 'B', title: 't', lines: [] },
      ],
      'barcode'
    )
    expect(h.match(/class="label/g)?.length).toBe(2)
  })
})
