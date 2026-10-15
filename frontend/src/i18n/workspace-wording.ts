/** 工作区文案检查：工作区用户不应感知多租户（不得出现“租户 / tenant / テナント”）。 */
import platformOnly from './platform-only-keys.json'

/** 禁止在工作区文案中出现的词。 */
export const TENANT_WORDING = /租户|tenant|テナント/i

/**
 * 该键是否只在平台管理控制台使用（允许出现租户字样）。
 *
 * @param key - 扁平化的 i18n 键（如 `members.desc`）
 */
export const isPlatformOnly = (key: string) =>
  platformOnly.keys.includes(key) ||
  platformOnly.prefixes.some((p) => key.startsWith(p))

/**
 * 找出包含租户字样的工作区键。
 *
 * @param bundle - 语言包对象
 * @returns `key = value` 列表
 */
export function tenantWordingLeaks(bundle: object): string[] {
  const out: string[] = []
  const walk = (o: Record<string, unknown>, p: string) => {
    for (const [k, v] of Object.entries(o)) {
      const key = p + k
      if (v && typeof v === 'object')
        walk(v as Record<string, unknown>, key + '.')
      else if (
        typeof v === 'string' &&
        TENANT_WORDING.test(v) &&
        !isPlatformOnly(key)
      )
        out.push(`${key} = ${v}`)
    }
  }
  walk(bundle as Record<string, unknown>, '')
  return out
}
