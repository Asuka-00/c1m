/**
 * 后端菜单 key 清单：直接读取后端提交的 `backend/app/platform/menus/menu_keys.json`
 * （be/p2 46e3da6 起入库，后端测试保证与代码一致；本文件夹的 menu-keys.json 是它的拷贝）。
 * 后端增删菜单时重新拷贝 JSON，下面三组 key 自动派生：
 * - BACKEND_MENU_KEYS：workspace 空间的分组 / 菜单 / 页签
 * - PLATFORM_MENU_KEYS：platform 空间
 * - TAB_ONLY_MENU_KEYS：kind=tab（只作 tabs / tree 页签，没有独立路由；跳父页面并带 tab）
 * /menus/me 只返回英文标题，界面文字全靠前端语言包 menu.<key>，因此每个 key 都必须有三语翻译。
 */
import data from './menu-keys.json'

export interface MenuKeyItem {
  key: string
  space: 'workspace' | 'platform'
  kind: 'group' | 'item' | 'tab'
  parent: string | null
  path: string | null
  component: string | null
  permission: string | null
  i18n_key: string
  titles: Record<string, string>
}

export const MENU_KEY_ITEMS = data.items as MenuKeyItem[]

const keys = (f: (i: MenuKeyItem) => boolean) =>
  MENU_KEY_ITEMS.filter(f).map((i) => i.key)

export const BACKEND_MENU_KEYS = keys((i) => i.space === 'workspace')

export const PLATFORM_MENU_KEYS = keys((i) => i.space === 'platform')

export const TAB_ONLY_MENU_KEYS = keys((i) => i.kind === 'tab')

/** 前端已用、后端 JSON 尚未落地的 key（手写，待与后端对齐）。 */
export const PENDING_MENU_KEYS: readonly string[] = [
  'g-exception',
  'mes-ct-move-report',
  'mes-qual-expiring',
]
