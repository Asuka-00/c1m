#!/usr/bin/env node
// 工作区文案检查：除 src/i18n/platform-only-keys.json 列出的平台控制台键外，
// 任何语言包（含生成的 MES 包）的值都不得包含“租户 / tenant / テナント”。
import { readFileSync } from 'node:fs'

const dir = new URL('../src/i18n/', import.meta.url).pathname
const { prefixes, keys } = JSON.parse(readFileSync(dir + 'platform-only-keys.json', 'utf8'))
const RE = /租户|tenant|テナント/i
const allowed = (k) => keys.includes(k) || prefixes.some((p) => k.startsWith(p))
let bad = 0
for (const f of ['zh-CN', 'en', 'ja', 'mes/zh-CN', 'mes/en', 'mes/ja']) {
  const walk = (o, p) => {
    for (const [k, v] of Object.entries(o)) {
      if (v && typeof v === 'object') walk(v, `${p}${k}.`)
      else if (typeof v === 'string' && RE.test(v) && !allowed(p + k)) {
        bad++
        console.error(`✗ ${f}: ${p}${k} = ${v}`)
      }
    }
  }
  walk(JSON.parse(readFileSync(`${dir}locales/${f}.json`, 'utf8')), '')
}
if (bad) {
  console.error(`${bad} workspace i18n value(s) mention tenants`)
  process.exit(1)
}
console.log('workspace wording OK: no tenant wording outside the platform console')
