/** 标签打印工具：条码（Code 128）/ 二维码 SVG 与可打印页面 HTML。 */
import JsBarcode from 'jsbarcode'
import QRCode from 'qrcode'

/** 一张标签：编码（条码内容）、标题与附加行。 */
export interface LabelData {
  code: string
  title: string
  lines: string[]
  hot?: boolean
}

/** 码制：条码、二维码或两者。 */
export type CodeKind = 'barcode' | 'qr' | 'both'

const esc = (s: string) =>
  s.replace(
    /[&<>"']/g,
    (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[
        c
      ] as string
  )

/** Code 128 条码 SVG 字符串。 */
export function barcodeSvg(text: string): string {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  JsBarcode(svg, text, {
    format: 'CODE128',
    height: 40,
    width: 1.6,
    fontSize: 12,
    margin: 0,
    displayValue: false,
  })
  return svg.outerHTML
}

/** 二维码 SVG 字符串。 */
export function qrSvg(text: string): Promise<string> {
  return QRCode.toString(text, { type: 'svg', margin: 0, width: 72 })
}

/** 单张标签 HTML（码图 + 编码 + 附加行）。 */
export async function labelHtml(l: LabelData, kind: CodeKind): Promise<string> {
  const bar =
    kind !== 'qr' ? `<div class="bar">${barcodeSvg(l.code)}</div>` : ''
  const qr =
    kind !== 'barcode' ? `<div class="qr">${await qrSvg(l.code)}</div>` : ''
  return (
    `<div class="label${l.hot ? ' hot' : ''}">${qr}<div class="body">` +
    `<div class="code">${esc(l.code)}${l.hot ? ' <b>HOT</b>' : ''}</div>` +
    `<div class="title">${esc(l.title)}</div>` +
    l.lines.map((x) => `<div class="line">${esc(x)}</div>`).join('') +
    `${bar}</div></div>`
  )
}

/** 可打印页面（每张标签 70 × 35 mm，自动换行排布）。 */
export async function printHtml(
  labels: LabelData[],
  kind: CodeKind
): Promise<string> {
  const body = (await Promise.all(labels.map((l) => labelHtml(l, kind)))).join(
    ''
  )
  return `<!doctype html><html><head><meta charset="utf-8"><title>Labels</title><style>
@page{margin:6mm}body{font-family:sans-serif;margin:0;display:flex;flex-wrap:wrap;gap:3mm}
.label{width:70mm;height:35mm;box-sizing:border-box;border:1px solid #999;border-radius:2mm;padding:2mm;display:flex;gap:2mm;overflow:hidden;break-inside:avoid}
.label.hot{border:2px solid #dc2626}.qr svg{width:22mm;height:22mm}.body{flex:1;min-width:0}
.code{font:bold 12pt monospace}.code b{color:#fff;background:#dc2626;padding:0 3px;font-size:8pt}
.title{font-size:8pt}.line{font-size:7pt;color:#333}.bar svg{max-width:100%;height:9mm}
</style></head><body>${body}</body></html>`
}
