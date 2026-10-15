import { type LinkProps } from '@tanstack/react-router'

type BaseNavItem = {
  title: string
  badge?: string
  icon?: React.ElementType
}

type NavLink = BaseNavItem & {
  url: LinkProps['to'] | (string & {})
  items?: never
}

type NavCollapsible = BaseNavItem & {
  /** 用于持久化展开 / 折叠状态的稳定 id */
  key?: string
  items: (BaseNavItem & { url: LinkProps['to'] | (string & {}) })[]
  url?: never
}

type NavItem = NavCollapsible | NavLink

type NavGroup = {
  title: string
  items: NavItem[]
}

export type { NavGroup, NavItem, NavCollapsible, NavLink }
