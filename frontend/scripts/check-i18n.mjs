#!/usr/bin/env node
// 语言包检查（locales/<语言>/**/*.yaml）：
// 1. 各语言的文件结构一致；
// 2. 各语言键完全一致（以 zh-CN 为基准）、值非空、{{占位符}} 一致；
// 3. 代码里静态使用的 t('key') 都存在；
// 4. 后端对外的全部 code（src/i18n/backend-codes.json，由 backend/scripts/export_i18n_codes.py 生成：
//    错误码 error.code_<n>、实体 / 字段 / 枚举 / 菜单 / 权限 / 通知 / 检查消息 / 系统说明）都有译文。
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { LOCALES, flat, loadLocale, localeFiles } from './lib/locales.mjs'

const data = Object.fromEntries(LOCALES.map((l) => [l, new Map(flat(loadLocale(l)))]))
let errors = 0
const fail = (m) => {
  errors++
  console.error('✗', m)
}
const ref = data['zh-CN']
const vars = (s) => [...String(s).matchAll(/{{\s*(\w+)\s*}}/g)].map((m) => m[1]).sort().join(',')

// 文件结构
const refFiles = localeFiles('zh-CN').join('|')
for (const l of LOCALES) if (localeFiles(l).join('|') !== refFiles) fail(`${l}: locale files differ from zh-CN`)

for (const l of LOCALES) {
  for (const k of ref.keys()) if (!data[l].has(k)) fail(`${l}: missing key "${k}"`)
  for (const [k, v] of data[l]) {
    if (!ref.has(k)) fail(`${l}: extra key "${k}" (not in zh-CN)`)
    if (typeof v !== 'string' || !v.trim()) fail(`${l}: empty value for "${k}"`)
    else if (ref.has(k) && vars(v) !== vars(ref.get(k))) fail(`${l}: placeholders differ for "${k}"`)
  }
}
// 后端 code 清单
const codes = JSON.parse(
  readFileSync(new URL('../src/i18n/backend-codes.json', import.meta.url), 'utf8')
)
for (const k of codes) if (!ref.has(k)) fail(`backend code without translation: "${k}"`)
// 代码里静态使用的键
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
console.log(`i18n OK: ${ref.size} keys × ${LOCALES.length} locales (${LOCALES.join(', ')}), ${refFiles.split('|').length} files each`)
