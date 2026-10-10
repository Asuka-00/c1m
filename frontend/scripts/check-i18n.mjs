#!/usr/bin/env node
// Checks that every locale has exactly the same keys (zh-CN is the reference,
// en and ja must match), that no value is empty, that {{placeholders}} match,
// and that every static t('key') used in src/ exists.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const dir = new URL('../src/i18n/locales/', import.meta.url).pathname
const LOCALES = ['zh-CN', 'ja', 'en']
const flat = (o, p = '') =>
  Object.entries(o).flatMap(([k, v]) =>
    v && typeof v === 'object' ? flat(v, `${p}${k}.`) : [[`${p}${k}`, v]]
  )
const data = Object.fromEntries(
  LOCALES.map((l) => [l, new Map(flat(JSON.parse(readFileSync(join(dir, `${l}.json`), 'utf8'))))])
)
let errors = 0
const fail = (m) => {
  errors++
  console.error('✗', m)
}
const ref = data['zh-CN']
const vars = (s) => [...String(s).matchAll(/{{\s*(\w+)\s*}}/g)].map((m) => m[1]).sort().join(',')
for (const l of LOCALES) {
  for (const k of ref.keys()) if (!data[l].has(k)) fail(`${l}: missing key "${k}"`)
  for (const [k, v] of data[l]) {
    if (!ref.has(k)) fail(`${l}: extra key "${k}" (not in zh-CN)`)
    if (typeof v !== 'string' || !v.trim()) fail(`${l}: empty value for "${k}"`)
    else if (ref.has(k) && vars(v) !== vars(ref.get(k))) fail(`${l}: placeholders differ for "${k}"`)
  }
}
// static keys used in code
const walk = (d) =>
  readdirSync(d).flatMap((f) => {
    const p = join(d, f)
    return statSync(p).isDirectory() ? walk(p) : /\.(tsx?|jsx?)$/.test(f) ? [p] : []
  })
const src = new URL('../src/', import.meta.url).pathname
for (const file of walk(src)) {
  const code = readFileSync(file, 'utf8')
  for (const m of code.matchAll(/\bt\(\s*'([^'$`]+)'/g)) {
    if (!ref.has(m[1])) fail(`${file.replace(src, 'src/')}: unknown key "${m[1]}"`)
  }
}
if (errors) {
  console.error(`\n${errors} i18n problem(s)`)
  process.exit(1)
}
console.log(`i18n OK: ${ref.size} keys × ${LOCALES.length} locales (${LOCALES.join(', ')})`)
