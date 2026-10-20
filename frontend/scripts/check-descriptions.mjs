#!/usr/bin/env node
// 说明类文案检查（规则同 src/i18n/description-style.ts）：副标题 / 说明 / 帮助 / 空状态 / 提示
// 不得含环境变量样式的标记（UPPER_SNAKE）、“API”，且中日文不超过 40 字、拉丁文不超过 100 字符。
import { LOCALES, loadLocale } from './lib/locales.mjs'

const isDesc = (k) =>
  /(desc|hint|help|empty|tooltip|subtitle|tip)[^.]*$/i.test(k.split('.').pop()) ||
  /\.(descs|hints|help|tips)\./i.test(k)
const problem = (s) => {
  if (/\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/.test(s)) return 'env-var-like token'
  if (/\bAPI\b/.test(s)) return 'mentions API'
  const cjk = (s.match(/[\u3040-\u30ff\u4e00-\u9fff]/g) ?? []).length
  return (cjk ? cjk > 40 : s.length > 100) ? 'too long' : null
}
let bad = 0
for (const f of LOCALES) {
  const walk = (o, p) => {
    for (const [k, v] of Object.entries(o)) {
      const key = p + k
      if (key.startsWith('error.')) continue
      if (v && typeof v === 'object') walk(v, `${key}.`)
      else if (typeof v === 'string' && isDesc(key) && problem(v)) {
        bad++
        console.error(`✗ ${f}: ${key} (${problem(v)}) = ${v}`)
      }
    }
  }
  walk(loadLocale(f), '')
}
if (bad) {
  console.error(`${bad} description string(s) expose implementation details or are too long`)
  process.exit(1)
}
console.log('descriptions OK: short and free of implementation details')
