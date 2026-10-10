import {
  Building2,
  Circle,
  KeyRound,
  LayoutDashboard,
  Menu,
  Package,
  Settings,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  UserCog,
  Users,
  type LucideIcon,
} from 'lucide-react'

/** Icon names the backend menu registry may reference (lucide names). */
export const ICONS: Record<string, LucideIcon> = {
  Building2,
  KeyRound,
  LayoutDashboard,
  Menu,
  Package,
  Settings,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  UserCog,
  Users,
}
/** Fallback icons for menu groups that have none in the registry. */
const GROUP_ICONS: Record<string, LucideIcon> = {
  general: LayoutDashboard,
  tenant: Building2,
  admin: ShieldCheck,
  other: Settings,
}
export const groupIconFor = (
  key: string,
  name: string | null | undefined
): LucideIcon => (name && ICONS[name]) || GROUP_ICONS[key] || Circle

export const iconFor = (name: string | null | undefined): LucideIcon =>
  (name && ICONS[name]) || Circle
