/** 菜单索引（纯函数）：全局菜单搜索与面包屑共用。数据来自 GET /menus/me（已按权限过滤）。 */
import i18n, { LANGUAGES } from '@/i18n'
import type { MenuNode } from '@/lib/api'

/** 菜单 / 分组 / 页签在指定语言下的标题（menu.<key>，缺失时回退后端标题）。 */
export const menuTitle = (key: string, fallback: string, lng?: string) =>
  (lng ? i18n.getFixedT(lng) : i18n.t)(`menu.${key}`, {
    defaultValue: fallback,
  })

/** 可跳转的菜单项（独立菜单或合并菜单的页签）。 */
export interface MenuEntry {
  /** 唯一 id：菜单 key，页签为 `<菜单 key>:<页签 key>` */
  id: string
  key: string
  /** 后端标题（回退用） */
  fallback: string
  path: string
  /** 合并菜单的页签 key */
  tab?: string
  /** 所属合并菜单（页签项） */
  parent?: { key: string; title: string }
  /** 所属顶层分组 */
  group?: { key: string; title: string }
  /** 用于匹配的文本：三种语言的标题与 key（含所属合并菜单） */
  terms: string[]
}

const termsOf = (key: string, fallback: string) => [
  key,
  fallback,
  ...LANGUAGES.map((l) => menuTitle(key, fallback, l)),
]

/** 展开菜单树为可跳转项（按菜单顺序）。 */
export function menuEntries(menus: MenuNode[]): MenuEntry[] {
  const out: MenuEntry[] = []
  const walk = (ns: MenuNode[], group?: MenuNode) => {
    for (const n of ns) {
      const g = group ?? (n.children.length && !n.path ? n : undefined)
      const gi = g && { key: g.key, title: g.title }
      if (n.path && n.tabs?.length) {
        for (const tb of n.tabs)
          out.push({
            id: `${n.key}:${tb.key}`,
            key: tb.key,
            fallback: tb.title,
            path: n.path,
            tab: tb.key,
            parent: { key: n.key, title: n.title },
            group: gi,
            terms: [...termsOf(tb.key, tb.title), ...termsOf(n.key, n.title)],
          })
      } else if (n.path) {
        out.push({
          id: n.key,
          key: n.key,
          fallback: n.title,
          path: n.path,
          group: gi,
          terms: termsOf(n.key, n.title),
        })
      }
      walk(n.children, g)
    }
  }
  walk(menus)
  return out
}

const norm = (s: string) => s.toLowerCase().replace(/[\s\-_·・/（）()]/g, '')

/** 按关键字过滤（忽略大小写、空格与常见分隔符，任一语言标题或 key 包含即命中）。 */
export function matchEntries(entries: MenuEntry[], q: string): MenuEntry[] {
  const k = norm(q)
  if (!k) return entries
  return entries.filter((e) => e.terms.some((x) => norm(x).includes(k)))
}

/** 面包屑节点。 */
export interface Crumb {
  key: string
  title: string
  /** 可点击时的路径（分组无路径） */
  path?: string
}

/**
 * 由当前路由在菜单树中反查面包屑：分组 › 菜单 › 页签。
 * 合并菜单与页签同名（当前语言）时只显示一次；
 * 不在菜单树里但有 menu.<key> 文案的页面（如 /settings）只显示自身标题；其他未知路由返回空数组。
 *
 * @param menus - 当前用户菜单树
 * @param pathname - 当前路径
 * @param tab - URL 中的 `tab` 参数
 */
export function breadcrumbOf(
  menus: MenuNode[],
  pathname: string,
  tab?: unknown
): Crumb[] {
  const find = (ns: MenuNode[], chain: MenuNode[]): MenuNode[] | null => {
    for (const n of ns) {
      if (n.path && n.path === pathname) return [...chain, n]
      const hit = find(n.children, [...chain, n])
      if (hit) return hit
    }
    return null
  }
  const chain = find(menus, [])
  if (!chain) {
    // 不在菜单树里的页面（如 /settings、/notifications）：只显示页面自身标题，不挂分组
    const key = pathname.replace(/^\/+|\/+$/g, '').replace(/\//g, '-')
    return key && i18n.exists(`menu.${key}`)
      ? [{ key, title: i18n.t(`menu.${key}`) }]
      : []
  }
  const out: Crumb[] = chain.map((n) => ({
    key: n.key,
    title: menuTitle(n.key, n.title),
    path: n.path ?? undefined,
  }))
  const leaf = chain[chain.length - 1]
  const tabs = leaf.tabs ?? []
  const cur = tabs.find((x) => x.key === tab) ?? tabs[0]
  if (cur) {
    const title = menuTitle(cur.key, cur.title)
    if (title !== out[out.length - 1].title) out.push({ key: cur.key, title })
  }
  return out
}
