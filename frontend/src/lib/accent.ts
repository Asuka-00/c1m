/**
 * Brand accent -> theme CSS variables. The colour is a hex string from the
 * effective branding (`primary_color`); unset/invalid keeps the default theme.
 */

const HEX = /^#(?:[0-9a-f]{3}){1,2}$/i
const STYLE_ID = 'brand-accent'

type RGB = [number, number, number]

export function parseHex(hex: string | null | undefined): RGB | null {
  if (!hex || !HEX.test(hex)) return null
  let h = hex.slice(1)
  if (h.length === 3) h = [...h].map((c) => c + c).join('')
  const n = parseInt(h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

/** WCAG relative luminance (0..1) */
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

/** foreground with the better contrast against `bg` */
export function foregroundFor(bg: RGB): string {
  const l = luminance(bg)
  return contrast(l, 1) >= contrast(l, 0) ? '#ffffff' : '#0a0a0a'
}

/** dark mode: lift very dark accents so they stay visible on dark surfaces */
export function darkVariant(c: RGB): RGB {
  let out = c
  for (let i = 0; i < 10 && contrast(luminance(out), 0.012) < 3; i++)
    out = mix(out, WHITE, 0.15)
  return out
}

/** light mode: deepen very light accents so they are visible on white */
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

/** CSS for both modes, or null for the default theme */
export function accentCss(color: string | null | undefined): string | null {
  const c = parseHex(color)
  if (!c) return null
  // html:root / html.dark beat theme.css's :root / .dark regardless of order
  return `html:root { ${vars(lightVariant(c))} }\nhtml.dark { ${vars(darkVariant(c))} }`
}

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
