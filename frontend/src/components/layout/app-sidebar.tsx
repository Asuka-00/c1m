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

/** Menu titles: translated by menu key (menu.<key>), falling back to the backend title. */
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

/** Sidebar built ONLY from GET /menus/me. Top-level nodes with children are
 *  collapsible groups (collapsed by default; the one holding the active route
 *  auto-expands); top-level leaves are plain links. */
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
