/** 平台管理控制台接口（/platform/...，仅超级用户；其他用户 403）。 */
import { del, get, patch, post, put, type ListQuery } from '../request'
import type {
  ConfigGroup,
  CrossTenantAudit,
  LoginLog,
  Member,
  Message,
  NotifyChannel,
  Paged,
  PlatformAudit,
  PlatformTenant,
  Role,
  Token,
} from '../types'

/** 平台创建 / 更新租户的请求体。 */
interface PlatformTenantIn {
  name?: string
  slug?: string
  status?: string
  plan?: string
  expires_at?: string | null
  owner_email?: string | null
}

/** 平台控制台接口。 */
export const platformApi = {
  tenants: (q: ListQuery) => get<Paged<PlatformTenant>>('/platform/tenants', q),
  createTenant: (b: PlatformTenantIn) =>
    post<PlatformTenant>('/platform/tenants', b),
  updateTenant: (id: string, b: PlatformTenantIn) =>
    patch<PlatformTenant>(`/platform/tenants/${id}`, b),
  removeTenant: (id: string) => del<Message>(`/platform/tenants/${id}`),
  /** 以租户身份进入：返回绑定该租户的令牌（服务端记入平台操作日志） */
  enterTenant: (id: string) => post<Token>(`/platform/tenants/${id}/enter`),
  /** 退出租户模拟（恢复原令牌后调用，记入平台操作日志） */
  exitTenant: (id: string) => post<Message>(`/platform/tenants/${id}/exit`),
  members: (id: string, q: ListQuery) =>
    get<Paged<Member>>(`/platform/tenants/${id}/members`, q),
  tenantRoles: (id: string, q: ListQuery) =>
    get<Paged<Role>>(`/platform/tenants/${id}/roles`, q),
  addMember: (id: string, b: { email: string; roles: string[] }) =>
    post<Member>(`/platform/tenants/${id}/members`, b),
  setMemberRoles: (id: string, userId: string, roles: string[]) =>
    put<Member>(`/platform/tenants/${id}/members/${userId}/roles`, { roles }),
  removeMember: (id: string, userId: string) =>
    del<Message>(`/platform/tenants/${id}/members/${userId}`),
  assignOwner: (id: string, email: string) =>
    put<Member>(`/platform/tenants/${id}/owner`, { email }),
  branding: (id: string) =>
    get<Paged<ConfigGroup>>(`/platform/tenants/${id}/branding`),
  updateBranding: (id: string, code: string, values: Record<string, unknown>) =>
    patch<ConfigGroup>(`/platform/tenants/${id}/branding/${code}`, { values }),
  channels: () => get<Paged<NotifyChannel>>('/platform/notify-channels'),
  setChannel: (code: string, enabled: boolean) =>
    put<NotifyChannel>(`/platform/notify-channels/${code}`, { enabled }),
  loginLog: (q: ListQuery) => get<Paged<LoginLog>>('/platform/login-log', q),
  opsLog: (q: ListQuery) => get<Paged<PlatformAudit>>('/platform/ops-log', q),
  audit: (q: ListQuery) => get<Paged<CrossTenantAudit>>('/platform/audit', q),
}
