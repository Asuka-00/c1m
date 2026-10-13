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

/** 菜单节点转为侧栏项：带子项的节点为可折叠分组（递归支持多级），其余为链接。 */
function toNavItem(n: MenuNode, top = false): NavItem {
  if (n.children.length)
    return {
      key: n.key,
      title: title(n),
      icon: top ? groupIconFor(n.key, n.icon) : iconFor(n.icon),
      items: n.children.map((c) => toNavItem(c)),
    }
  return { title: title(n), url: n.path ?? '#', icon: iconFor(n.icon) }
}

/** 侧栏完全由 GET /menus/me 构建。带子项的节点为可折叠分组（手风琴：
 *  只展开当前页面所在分组的祖先链，打开一个分组会收起其他分组，支持多级）；
 *  顶层叶子节点为普通链接。 */
export function AppSidebar() {
  const { collapsible, variant } = useLayout()
  const { data, isLoading } = useMyMenus()
  const items: NavItem[] = (data?.menus ?? []).map((g) => toNavItem(g, true))
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
