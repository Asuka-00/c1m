import { t } from '@/i18n'
import type { MenuNode } from '@/lib/api'
import { useMyMenus } from '@/lib/api/hooks'
import { useLayout } from '@/context/layout-provider'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from '@/components/ui/sidebar'
import { Skeleton } from '@/components/ui/skeleton'
import { groupIconFor, iconFor } from './icons'
import { NavGroup } from './nav-group'
import { NavUser } from './nav-user'
import { TeamSwitcher } from './team-switcher'
import type { NavItem } from './types'

/** 菜单标题：按菜单 key 翻译（menu.<key>），缺失时回退到后端标题。 */
const title = (n: MenuNode) => t(`menu.${n.key}`, { defaultValue: n.title })

function toNavItem(n: MenuNode): NavItem {
  if (n.children.length)
    return {
      title: title(n),
      icon: iconFor(n.icon),
      items: n.children.map((c) => ({
        title: title(c),
        url: c.path ?? '#',
        icon: iconFor(c.icon),
      })),
    }
  return { title: title(n), url: n.path ?? '#', icon: iconFor(n.icon) }
}

/** 侧栏完全由 GET /menus/me 构建。带子项的顶层节点为
 *  可折叠分组（默认折叠，包含当前路由的分组
 *  自动展开）；顶层叶子节点为普通链接。 */
export function AppSidebar() {
  const { collapsible, variant } = useLayout()
  const { data, isLoading } = useMyMenus()
  const items: NavItem[] = (data?.menus ?? []).map((g) =>
    g.children.length
      ? {
          key: g.key,
          title: title(g),
          icon: groupIconFor(g.key, g.icon),
          items: g.children.map((c) => ({
            title: title(c),
            url: c.path ?? '#',
            icon: iconFor(c.icon),
          })),
        }
      : toNavItem(g)
  )
  return (
    <Sidebar collapsible={collapsible} variant={variant}>
      <SidebarHeader>
        <TeamSwitcher />
      </SidebarHeader>
      <SidebarContent>
        {isLoading ? (
          <div className='space-y-2 p-4'>
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className='h-6' />
            ))}
          </div>
        ) : (
          <NavGroup title='' items={items} />
        )}
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
