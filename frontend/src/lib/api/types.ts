export type UUID = string

export interface User {
  id: UUID
  email: string
  username: string | null
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  created_at: string | null
}
export interface Paged<T> {
  data: T[]
  count: number
}
export interface Permission {
  id: UUID
  code: string
  description: string | null
  scope: 'platform' | 'tenant' | string
}
export interface Role {
  id: UUID
  name: string
  description: string | null
  tenant_id: UUID | null
  permissions: Permission[]
}
export interface Tenant {
  id: UUID
  name: string
  slug: string
  status: string
  created_at: string | null
}
export interface MyTenant {
  tenant: Tenant
  roles: string[]
  permissions: string[]
}
export interface Member {
  user_id: UUID
  email: string
  full_name: string | null
  roles: string[]
}
export interface MenuNode {
  key: string
  title: string
  path: string | null
  icon: string | null
  component: string | null
  permission: string | null
  children: MenuNode[]
}
export interface MyMenus {
  menus: MenuNode[]
  forbidden_paths: string[]
  permissions: string[]
  tenant_id: UUID | null
  is_superuser: boolean
}
export interface Menu {
  id: UUID
  key: string
  title: string
  path: string | null
  icon: string | null
  component: string | null
  sort_order: number
  permission: string | null
  hidden: boolean
  parent_id: UUID | null
}
export interface Message {
  message: string
}

export type ConfigValueType =
  | 'string'
  | 'text'
  | 'number'
  | 'boolean'
  | 'select'
  | 'color'
  | 'url'
  | 'image'
  | 'file'
  | 'json'

export interface ConfigItem {
  id: string
  code: string
  name: string
  description: string | null
  value_type: ConfigValueType
  value: unknown
  default_value: unknown
  options: { value: string; label: string }[] | null
  validation: Record<string, unknown> | null
  is_public: boolean
  tenant_overridable: boolean
  sort_order: number
  /** tenant view: inherited platform value and whether the tenant overrides it */
  platform_value: unknown
  overridden: boolean
}

export interface ConfigGroup {
  id: string
  code: string
  name: string
  name_key: string | null
  description: string | null
  sort_order: number
  items: ConfigItem[]
}

export type PublicConfig = Record<string, Record<string, unknown>>

export interface UploadedFile {
  id: string
  url: string
  filename: string
  content_type: string
  size: number
  tenant_id: string | null
}
