/** 合并菜单的纯函数工具：选择页签、解析旧路径重定向。 */
import { t } from '@/i18n'
import type { MenuTab } from '@/lib/api'

/** 改名前的页签 key -> 新 key（旧链接 `?tab=` 仍可用）。 */
const LEGACY_TABS: Record<string, string> = { 'tenant-roles': 'user-roles' }

/**
 * 当前页签：URL 中的 `tab` 存在且可见时取之，否则取第一个可见页签。
 *
 * @param tabs - 已按权限过滤的页签
 * @param tab - URL 中的 tab 参数
 */
export function pickTab(tabs: MenuTab[], tab: unknown): MenuTab | undefined {
  const key = typeof tab === 'string' ? (LEGACY_TABS[tab] ?? tab) : tab
  return tabs.find((x) => x.key === key) ?? tabs[0]
}

/**
 * 旧路径重定向：返回新路径与合并后的查询参数（保留原参数，如 `?id=`）。
 *
 * @param redirects - 旧路径 -> `新路径?tab=key`
 * @param path - 当前路径
 * @param search - 当前查询参数
 * @returns 目标；无需重定向时为 null
 */
export function resolveRedirect(
  redirects: Record<string, string> | undefined,
  path: string,
  search: Record<string, unknown> = {}
): { path: string; search: Record<string, unknown> } | null {
  const to = redirects?.[path]
  if (!to) return null
  const [p, qs = ''] = to.split('?')
  const extra = Object.fromEntries(new URLSearchParams(qs))
  return { path: p, search: { ...search, ...extra } }
}

/**
 * 页签 / 合并菜单标题（菜单 i18n，缺省用后端标题）。
 *
 * @param key - 菜单 key
 * @param title - 后端标题
 */
export const tabTitle = (key: string, title: string) =>
  t(`menu.${key}`, { defaultValue: title })
