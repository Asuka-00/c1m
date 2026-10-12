/**
 * 基于 document.cookie 的 Cookie 工具函数
 * 替代 js-cookie 依赖，行为更一致
 */

const DEFAULT_MAX_AGE = 60 * 60 * 24 * 7 // 7 天

/**
 * 按名称读取 Cookie
 */
export function getCookie(name: string): string | undefined {
  if (typeof document === 'undefined') return undefined

  const value = `; ${document.cookie}`
  const parts = value.split(`; ${name}=`)
  if (parts.length === 2) {
    const cookieValue = parts.pop()?.split(';').shift()
    return cookieValue
  }
  return undefined
}

/**
 * 设置 Cookie（名称、值、可选有效期）
 */
export function setCookie(
  name: string,
  value: string,
  maxAge: number = DEFAULT_MAX_AGE
): void {
  if (typeof document === 'undefined') return

  document.cookie = `${name}=${value}; path=/; max-age=${maxAge}`
}

/**
 * 通过把有效期设为 0 删除 Cookie
 */
export function removeCookie(name: string): void {
  if (typeof document === 'undefined') return

  document.cookie = `${name}=; path=/; max-age=0`
}
