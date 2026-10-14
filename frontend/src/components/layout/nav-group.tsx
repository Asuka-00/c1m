import { type ReactNode, useMemo, useState } from 'react'
import { Link, useLocation } from '@tanstack/react-router'
import { ChevronRight } from 'lucide-react'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from '@/components/ui/sidebar'
import { Badge } from '../ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import { type AccordionNode, activeChain, toggleGroup } from './accordion'
import {
  type NavCollapsible,
  type NavItem,
  type NavLink,
  type NavGroup as NavGroupProps,
} from './types'

/** 子菜单项允许换行：长名称（如「Future Hold（预约 Hold）」）不被截断，高度随内容增长。 */
const SUB_WRAP = 'h-auto min-h-7 py-1'
/** 覆盖按钮里 `[&>span:last-child]:truncate` 的单行截断。 */
const LABEL_WRAP = 'whitespace-normal! [overflow-wrap:anywhere]'

/** 分组 id（key 优先，回退到标题）。 */
const groupId = (item: NavCollapsible) => item.key ?? item.title

/** 菜单项转为手风琴树节点。 */
function toNodes(items: NavItem[]): AccordionNode[] {
  return items.map((i) =>
    i.items
      ? { id: groupId(i), children: toNodes(i.items) }
      : { id: `${i.title}-${String(i.url)}`, url: String(i.url) }
  )
}

/**
 * 侧栏中的一组菜单（标题 + 菜单项）。分组为手风琴：同时只展开一条祖先链，
 * 展开某分组会收起其他分组；路由变化时自动展开当前页面所在分组并收起其余分组；
 * 再次点击已展开的分组可将其收起。
 */
export function NavGroup({ title, items }: NavGroupProps) {
  const { state, isMobile } = useSidebar()
  const href = useLocation({ select: (location) => location.href })
  const path = href.split('?')[0]
  const nodes = useMemo(() => toNodes(items), [items])
  const [open, setOpen] = useState<string[]>(() => activeChain(nodes, path))
  // 路由变化（或菜单加载完成）时同步到当前页面所在分组（渲染期间调整状态，不使用 effect）
  const sig = `${path}|${nodes.length}`
  const [seen, setSeen] = useState(sig)
  if (sig !== seen) {
    setSeen(sig)
    const chain = activeChain(nodes, path)
    if (chain.length) setOpen(chain)
  }
  const onToggle = (id: string, next: boolean) =>
    setOpen((o) => toggleGroup(nodes, o, id, next))
  return (
    <SidebarGroup>
      {title && <SidebarGroupLabel>{title}</SidebarGroupLabel>}
      <SidebarMenu>
        {items.map((item) => {
          const key = `${item.title}-${item.url}`

          if (!item.items)
            return <SidebarMenuLink key={key} item={item} href={href} />

          if (state === 'collapsed' && !isMobile)
            return (
              <SidebarMenuCollapsedDropdown key={key} item={item} href={href} />
            )

          return (
            <SidebarMenuCollapsible
              key={key}
              item={item}
              href={href}
              open={open}
              onToggle={onToggle}
            />
          )
        })}
      </SidebarMenu>
    </SidebarGroup>
  )
}

function NavBadge({ children }: { children: ReactNode }) {
  return <Badge className='rounded-full px-1 py-0 text-xs'>{children}</Badge>
}

function SidebarMenuLink({ item, href }: { item: NavLink; href: string }) {
  const { setOpenMobile } = useSidebar()
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        asChild
        isActive={checkIsActive(href, item)}
        tooltip={item.title}
      >
        <Link to={item.url} onClick={() => setOpenMobile(false)}>
          {item.icon && <item.icon />}
          <span>{item.title}</span>
          {item.badge && <NavBadge>{item.badge}</NavBadge>}
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}

/** 分组下的全部叶子链接（多级分组展平，用于折叠侧栏的下拉菜单）。 */
const leaves = (item: NavCollapsible): NavLink[] =>
  item.items.flatMap((i) => (i.items ? leaves(i) : [i]))

/** 当前路径属于该分组的子项（或其下级）时为 true */
const containsActive = (href: string, item: NavCollapsible) => {
  const path = href.split('?')[0]
  return leaves(item).some(
    (i) =>
      typeof i.url === 'string' &&
      (path === i.url || (i.url !== '/' && path.startsWith(`${i.url}/`)))
  )
}

/** 可折叠菜单分组（手风琴，展开状态由 NavGroup 统一管理；支持多级分组）。 */
function SidebarMenuCollapsible({
  item,
  href,
  open,
  onToggle,
  nested = false,
}: {
  item: NavCollapsible
  href: string
  open: string[]
  onToggle: (id: string, next: boolean) => void
  nested?: boolean
}) {
  const { setOpenMobile } = useSidebar()
  const id = groupId(item)
  const isOpen = open.includes(id)
  const Item = nested ? SidebarMenuSubItem : SidebarMenuItem
  const Button = nested ? SidebarMenuSubButton : SidebarMenuButton
  return (
    <Collapsible
      asChild
      open={isOpen}
      onOpenChange={(next) => onToggle(id, next)}
      className='group/collapsible'
    >
      <Item data-group={id}>
        <CollapsibleTrigger asChild>
          <Button
            {...(nested ? {} : { tooltip: item.title })}
            data-group-trigger={id}
            className='cursor-pointer'
          >
            {item.icon && <item.icon />}
            <span>{item.title}</span>
            {item.badge && <NavBadge>{item.badge}</NavBadge>}
            <ChevronRight className='ms-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90 rtl:rotate-180' />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className='CollapsibleContent'>
          <SidebarMenuSub>
            {item.items.map((subItem) =>
              subItem.items ? (
                <SidebarMenuCollapsible
                  key={groupId(subItem)}
                  item={subItem}
                  href={href}
                  open={open}
                  onToggle={onToggle}
                  nested
                />
              ) : (
                <SidebarMenuSubItem key={subItem.title}>
                  <SidebarMenuSubButton
                    asChild
                    isActive={checkIsActive(href, subItem)}
                    className={SUB_WRAP}
                  >
                    <Link
                      to={subItem.url}
                      title={subItem.title}
                      onClick={() => setOpenMobile(false)}
                    >
                      {subItem.icon && <subItem.icon />}
                      <span className={LABEL_WRAP}>{subItem.title}</span>
                      {subItem.badge && <NavBadge>{subItem.badge}</NavBadge>}
                    </Link>
                  </SidebarMenuSubButton>
                </SidebarMenuSubItem>
              )
            )}
          </SidebarMenuSub>
        </CollapsibleContent>
      </Item>
    </Collapsible>
  )
}

function SidebarMenuCollapsedDropdown({
  item,
  href,
}: {
  item: NavCollapsible
  href: string
}) {
  return (
    <SidebarMenuItem>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <SidebarMenuButton
            tooltip={item.title}
            isActive={containsActive(href, item)}
          >
            {item.icon && <item.icon />}
            <span>{item.title}</span>
            {item.badge && <NavBadge>{item.badge}</NavBadge>}
            <ChevronRight className='ms-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90' />
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent side='right' align='start' sideOffset={4}>
          <DropdownMenuLabel>
            {item.title} {item.badge ? `(${item.badge})` : ''}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {leaves(item).map((sub) => (
            <DropdownMenuItem key={`${sub.title}-${sub.url}`} asChild>
              <Link
                to={sub.url}
                className={`${checkIsActive(href, sub) ? 'bg-secondary' : ''}`}
              >
                {sub.icon && <sub.icon />}
                <span className='max-w-52 text-wrap'>{sub.title}</span>
                {sub.badge && (
                  <span className='ms-auto text-xs'>{sub.badge}</span>
                )}
              </Link>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  )
}

function checkIsActive(href: string, item: NavItem, mainNav = false) {
  return (
    href === item.url || // /endpoint?search=param 完全匹配
    href.split('?')[0] === item.url || // 忽略查询参数匹配
    !!item?.items?.filter((i) => i.url === href).length || // 子菜单处于激活状态
    (mainNav &&
      href.split('/')[1] !== '' &&
      href.split('/')[1] === item?.url?.split('/')[1])
  )
}
