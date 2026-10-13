/** 合并菜单的纯函数工具：选择页签、按菜单 key 定位页面。 */
import { t } from '@/i18n'
import type { MenuNode, MenuTab } from '@/lib/api'

/**
 * 当前页签：URL 中的 `tab` 存在且可见时取之，否则取第一个可见页签。
 *
 * @param tabs - 已按权限过滤的页签
 * @param tab - URL 中的 tab 参数
 */
export function pickTab(tabs: MenuTab[], tab: unknown): MenuTab | undefined {
  return tabs.find((x) => x.key === tab) ?? tabs[0]
}

/**
 * 按菜单 key 定位当前用户可见的页面：独立菜单返回其路径，合并菜单的页签返回合并页路径与 `tab`。
 *
 * @param menus - 当前用户的菜单树
 * @param key - 菜单 / 页签 key（如 `mes-product`）
 * @returns 页面位置；不可见时为 null
 */
export function findPage(
  menus: MenuNode[],
  key: string
): { path: string; tab?: string } | null {
  for (const n of menus) {
    if (n.path && n.key === key) return { path: n.path }
    if (n.path && n.tabs?.some((x) => x.key === key))
      return { path: n.path, tab: key }
    const hit = findPage(n.children, key)
    if (hit) return hit
  }
  return null
}

/**
 * 页签 / 合并菜单标题（菜单 i18n，缺省用后端标题）。
 *
 * @param key - 菜单 key
 * @param title - 后端标题
 */
export const tabTitle = (key: string, title: string) =>
  t(`menu.${key}`, { defaultValue: title })
