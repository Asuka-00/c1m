/**
 * 说明类文案检查：页面副标题、卡片说明、帮助、空状态与提示应为简短的功能描述，
 * 不暴露实现细节（环境变量、API、内部机制）。与 scripts/check-descriptions.mjs 规则一致。
 */

/** 说明类键：末段含 desc / hint / help / empty / tooltip / subtitle / tip，或位于 help 等分组下。 */
export const isDescriptionKey = (key: string) =>
  /(desc|hint|help|empty|tooltip|subtitle|tip)[^.]*$/i.test(
    key.split('.').pop() ?? ''
  ) || /\.(descs|hints|help|tips)\./i.test(key)

/** 最大长度：中日文 40 字，拉丁文 100 字符。 */
export const MAX_CJK = 40
export const MAX_LATIN = 100

const CJK = /[\u3040-\u30ff\u4e00-\u9fff]/g

/**
 * 说明文案的问题（无问题时返回 null）。
 *
 * @param text - 文案
 * @returns 问题描述
 */
export function descriptionProblem(text: string): string | null {
  if (/\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/.test(text)) return 'env-var-like token'
  if (/\bAPI\b/.test(text)) return 'mentions API'
  const cjk = (text.match(CJK) ?? []).length
  if (cjk ? cjk > MAX_CJK : text.length > MAX_LATIN) return 'too long'
  return null
}

/**
 * 语言包中不合规的说明文案（`backend.*` 为后端消息翻译，不在检查范围内）。
 *
 * @param bundle - 语言包
 * @returns `键: 问题` 列表
 */
export function descriptionIssues(bundle: object): string[] {
  const out: string[] = []
  const walk = (o: object, p: string) => {
    for (const [k, v] of Object.entries(o)) {
      const key = p + k
      if (key.startsWith('backend.')) continue
      if (v && typeof v === 'object') walk(v, `${key}.`)
      else if (typeof v === 'string' && isDescriptionKey(key)) {
        const why = descriptionProblem(v)
        if (why) out.push(`${key}: ${why}`)
      }
    }
  }
  walk(bundle, '')
  return out
}
