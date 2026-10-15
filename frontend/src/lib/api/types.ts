/** UUID 字符串。 */
export type UUID = string

/** 用户。 */
export interface User {
  id: UUID
  email: string
  username: string | null
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  created_at: string | null
}
/** 分页列表响应 `{data, count}`。 */
export interface Paged<T> {
  data: T[]
  count: number
}
/** 权限。 */
export interface Permission {
  id: UUID
  code: string
  description: string | null
  scope: 'platform' | 'tenant' | string
}
/** 角色（平台或租户）。 */
export interface Role {
  id: UUID
  name: string
  description: string | null
  tenant_id: UUID | null
  permissions: Permission[]
}
/** 租户。 */
export interface Tenant {
  id: UUID
  name: string
  slug: string
  status: string
  created_at: string | null
}
/** 当前用户的租户及其在该租户的角色。 */
export interface MyTenant {
  tenant: Tenant
  roles: string[]
  permissions: string[]
}
/** 租户成员。 */
export interface Member {
  user_id: UUID
  email: string
  full_name: string | null
  roles: string[]
}
/** 菜单树节点。 */
export interface MenuNode {
  key: string
  title: string
  path: string | null
  icon: string | null
  component: string | null
  permission: string | null
  children: MenuNode[]
}
/** 当前用户菜单：菜单树、权限与禁止访问的路径。 */
export interface MyMenus {
  menus: MenuNode[]
  forbidden_paths: string[]
  permissions: string[]
  tenant_id: UUID | null
  is_superuser: boolean
}
/** 菜单（管理视图）。 */
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
/** 通用消息响应。 */
export interface Message {
  message: string
}

/** 配置值类型。 */
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

/** 配置项。 */
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
  /** 租户视图：继承的平台值及租户是否已覆盖 */
  platform_value: unknown
  overridden: boolean
}

/** 配置分组。 */
export interface ConfigGroup {
  id: string
  code: string
  name: string
  name_key: string | null
  description: string | null
  sort_order: number
  items: ConfigItem[]
}

/** 公开配置（品牌等，无需登录）。 */
export type PublicConfig = Record<string, Record<string, unknown>>

/** 上传文件。 */
export interface UploadedFile {
  id: string
  url: string
  filename: string
  content_type: string
  size: number
  tenant_id: string | null
}
