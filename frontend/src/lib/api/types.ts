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
  /** 最后更新时间 / 更新人 */
  updated_at?: string | null
  updated_by?: string | null
  /** 平台角色名称 */
  role_names?: string[]
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
  /** 显示名称 */
  name?: string | null
  /** 类型：MENU / BUTTON / API */
  type?: PermType
  /** 所属菜单 id */
  menu_id?: UUID | null
  sort_order?: number
  /** active / disabled */
  status?: string
}
/** 权限类型。 */
export type PermType = 'MENU' | 'BUTTON' | 'API' | 'GROUP'
/** 统一权限树节点：菜单（kind=menu）、权限（kind=perm）或虚拟分组（kind=group）。 */
export interface PermNode {
  id: string
  kind: 'menu' | 'perm' | 'group'
  type: PermType
  key: string | null
  name: string
  code: string
  path: string | null
  icon: string | null
  component: string | null
  sort_order: number
  visible: boolean
  status: string
  scope: string | null
  space: string | null
  description: string | null
  /** 菜单：父菜单 id；权限：所属菜单 id */
  menu_id: string | null
  children: PermNode[]
}
/** 角色（平台或租户）。 */
export interface Role {
  id: UUID
  /** 角色编码 */
  name: string
  /** 角色名称（显示） */
  title?: string | null
  description: string | null
  /** active / disabled */
  status?: string
  tenant_id: UUID | null
  updated_at?: string | null
  updated_by?: string | null
  permissions: Permission[]
}
/** 租户。 */
export interface Tenant {
  id: UUID
  name: string
  slug: string
  status: string
  /** 套餐：trial / standard / enterprise */
  plan?: string
  /** 到期时间（null 表示永久） */
  expires_at?: string | null
  created_at: string | null
}
/** 平台视角的租户（含成员数与 owner）。 */
export interface PlatformTenant extends Tenant {
  plan: string
  expires_at: string | null
  member_count: number
  owners: string[]
}
/** 登录日志。 */
export interface LoginLog {
  id: UUID
  email: string
  user_id: UUID | null
  success: boolean
  reason: string | null
  ip: string | null
  user_agent: string | null
  created_at: string | null
}
/** 平台操作日志。 */
export interface PlatformAudit {
  id: UUID
  actor_email: string
  action: string
  target_type: string
  target_id: string | null
  tenant_id: UUID | null
  detail: Record<string, unknown> | null
  created_at: string | null
}
/** 跨租户业务审计行。 */
export interface CrossTenantAudit {
  id: string
  tenant_id: string
  tenant_name: string
  entity_type: string | null
  action: string | null
  record_code: string | null
  user_email: string | null
  changes: unknown
  created_at: string | null
}
/** 通知渠道（平台开关）。 */
export interface NotifyChannel {
  code: string
  label: string
  enabled: boolean
}
/** 访问令牌。 */
export interface Token {
  access_token: string
  token_type?: string
}
/** 菜单空间：租户工作区或平台管理控制台。 */
export type MenuSpace = 'workspace' | 'platform'
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
  username?: string | null
  is_active?: boolean
  roles: string[]
}
/** 菜单树节点。 */
export interface MenuNode {
  key: string
  title: string
  path: string | null
  icon: string | null
  component: string | null
  /** 权限编码；多个以逗号分隔表示“任一即可”（合并菜单） */
  permission: string | null
  /** 合并菜单的页签（已按权限过滤） */
  tabs?: MenuTab[]
  children: MenuNode[]
}
/** 合并菜单的页签（原独立菜单）。 */
export interface MenuTab {
  key: string
  title: string
  /** 原独立菜单路径（旧链接重定向到 合并页?tab=key） */
  path: string | null
  component: string | null
  permission: string | null
}
/** 当前用户菜单：菜单树、权限与禁止访问的路径。 */
export interface MyMenus {
  menus: MenuNode[]
  forbidden_paths: string[]
  /** 已并入合并菜单的旧路径 -> 新路径（含 ?tab=） */
  redirects?: Record<string, string>
  permissions: string[]
  tenant_id: UUID | null
  is_superuser: boolean
  /** 菜单所属空间 */
  space?: MenuSpace
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
  /** 所属空间（workspace / platform） */
  space?: MenuSpace
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
