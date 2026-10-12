/** System configuration (platform defaults, tenant overrides, public branding). */
import { del, get, patch } from '../request'
import type { ConfigGroup, Paged, PublicConfig } from '../types'

export const configApi = {
  /** platform defaults (platform config:read) */
  platform: () => get<Paged<ConfigGroup>>('/config/groups'),
  updatePlatform: (code: string, values: Record<string, unknown>) =>
    patch<ConfigGroup>(`/config/groups/${code}`, { values }),
  /** current tenant (X-Tenant-ID): effective values + inheritance info */
  tenant: () => get<Paged<ConfigGroup>>('/tenants/current/config'),
  updateTenant: (code: string, values: Record<string, unknown>) =>
    patch<ConfigGroup>(`/tenants/current/config/${code}`, { values }),
  resetTenantItem: (code: string, item: string) =>
    del<ConfigGroup>(`/tenants/current/config/${code}/${item}`),
  /** unauthenticated branding; tenant slug optional */
  public: (tenant?: string) =>
    get<PublicConfig>('/config/public', tenant ? { tenant } : undefined),
}
