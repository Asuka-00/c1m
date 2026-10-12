/**
 * 品牌强调色 -> 主题 CSS 变量。颜色为有效品牌配置中的十六进制字符串
 * （`primary_color`）；未设置 / 无效时保持默认主题。
 */

const HEX = /^#(?:[0-9a-f]{3}){1,2}$/i
const STYLE_ID = 'brand-accent'

type RGB = [number, number, number]

/** 解析 #RGB / #RRGGBB 颜色，无效时返回 null。 */
export function parseHex(hex: string | null | undefined): RGB | null {
  if (!hex || !HEX.test(hex)) return null
  let h = hex.slice(1)
  if (h.length === 3) h = [...h].map((c) => c + c).join('')
  const n = parseInt(h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

/** WCAG 相对亮度（0..1） */
export function luminance([r, g, b]: RGB): number {
  const lin = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

const contrast = (a: number, b: number) =>
  (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)

const hex = (c: RGB) =>
  '#' + c.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')
const mix = (a: RGB, b: RGB, t: number): RGB =>
  a.map((v, i) => v + (b[i] - v) * t) as RGB

const WHITE: RGB = [255, 255, 255]
const BLACK: RGB = [0, 0, 0]

/** 与 `bg` 对比度更好的前景色 */
export function foregroundFor(bg: RGB): string {
  const l = luminance(bg)
  return contrast(l, 1) >= contrast(l, 0) ? '#ffffff' : '#0a0a0a'
}

/** 暗色模式：提亮过暗的强调色，使其在深色背景上仍可见 */
export function darkVariant(c: RGB): RGB {
  let out = c
  for (let i = 0; i < 10 && contrast(luminance(out), 0.012) < 3; i++)
    out = mix(out, WHITE, 0.15)
  return out
}

/** 亮色模式：加深过浅的强调色，使其在白色背景上可见 */
export function lightVariant(c: RGB): RGB {
  let out = c
  for (let i = 0; i < 10 && contrast(luminance(out), 1) < 1.6; i++)
    out = mix(out, BLACK, 0.15)
  return out
}

function vars(c: RGB): string {
  const p = hex(c)
  const fg = foregroundFor(c)
  const ring = `color-mix(in oklab, ${p} 60%, transparent)`
  return [
    `--primary: ${p}`,
    `--primary-foreground: ${fg}`,
    `--ring: ${ring}`,
    `--sidebar-primary: ${p}`,
    `--sidebar-primary-foreground: ${fg}`,
    `--sidebar-ring: ${ring}`,
    `--chart-1: ${p}`,
  ].join('; ')
}

/** 两种模式的 CSS；默认主题时为 null */
export function accentCss(color: string | null | undefined): string | null {
  const c = parseHex(color)
  if (!c) return null
  // html:root / html.dark 的优先级高于 theme.css 的 :root / .dark，与顺序无关
  return `html:root { ${vars(lightVariant(c))} }\nhtml.dark { ${vars(darkVariant(c))} }`
}

/**
 * 把品牌强调色写入 `<style>` 标签（覆盖主题 CSS 变量）；无效或为空时移除。
 *
 * @param color - 十六进制颜色
 */
export function applyAccent(color: string | null | undefined): void {
  const css = accentCss(color)
  let el = document.getElementById(STYLE_ID)
  if (!css) {
    el?.remove()
    return
  }
  if (!el) {
    el = document.createElement('style')
    el.id = STYLE_ID
    document.head.appendChild(el)
  }
  el.textContent = css
}
