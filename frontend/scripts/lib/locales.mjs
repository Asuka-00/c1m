// 读取 src/i18n/locales/<语言>/**/*.yaml 并按语言深度合并（与 src/i18n/resources.ts 一致）。
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import YAML from 'yaml'

export const LOCALES = ['zh-CN', 'ja', 'en']
export const LOCALES_DIR = new URL('../../src/i18n/locales/', import.meta.url).pathname

const isObj = (x) => x && typeof x === 'object' && !Array.isArray(x)
const merge = (a, b) => {
  const out = { ...a }
  for (const [k, v] of Object.entries(b)) out[k] = isObj(v) && isObj(out[k]) ? merge(out[k], v) : v
  return out
}
const walk = (d) =>
  readdirSync(d).flatMap((f) => {
    const p = join(d, f)
    return statSync(p).isDirectory() ? walk(p) : f.endsWith('.yaml') ? [p] : []
  })

/** 某语言的 YAML 文件（相对语言目录，已排序）。 */
export const localeFiles = (lang) =>
  walk(join(LOCALES_DIR, lang)).map((p) => relative(join(LOCALES_DIR, lang), p)).sort()

/** 某语言合并后的完整语言树。 */
export function loadLocale(lang) {
  let tree = {}
  for (const f of localeFiles(lang))
    tree = merge(tree, YAML.parse(readFileSync(join(LOCALES_DIR, lang, f), 'utf8')))
  return tree
}

/** 展平为 [键路径, 值]。 */
export const flat = (o, p = '') =>
  Object.entries(o).flatMap(([k, v]) =>
    v && typeof v === 'object' ? flat(v, `${p}${k}.`) : [[`${p}${k}`, v]]
  )
