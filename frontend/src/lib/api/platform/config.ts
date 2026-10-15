/** 系统配置接口（平台默认值、租户覆盖值、公开品牌）。 */
import { del, get, patch } from '../request'
import type { ConfigGroup, Paged, PublicConfig } from '../types'

/** 系统配置接口。 */
export const configApi = {
  /** 平台默认值（平台空间，仅超级用户） */
  platform: () => get<Paged<ConfigGroup>>('/platform/config/groups'),
  updatePlatform: (code: string, values: Record<string, unknown>) =>
    patch<ConfigGroup>(`/platform/config/groups/${code}`, { values }),
  /** 当前租户（X-Tenant-ID）：有效值 + 继承信息 */
  tenant: () => get<Paged<ConfigGroup>>('/tenants/current/config'),
  updateTenant: (code: string, values: Record<string, unknown>) =>
    patch<ConfigGroup>(`/tenants/current/config/${code}`, { values }),
  resetTenantItem: (code: string, item: string) =>
    del<ConfigGroup>(`/tenants/current/config/${code}/${item}`),
  /** 无需登录的品牌信息；租户 slug 可选 */
  public: (tenant?: string) =>
    get<PublicConfig>('/config/public', tenant ? { tenant } : undefined),
}
