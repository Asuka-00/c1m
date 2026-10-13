/** 平台用户“所属租户”行的编解码（FormDialog 值只能是 string[]）。 */
import type { UserTenantRoles } from '@/lib/api'

/** 行编码为字符串数组（保留租户名用于显示不在下拉列表中的租户）。 */
export const encodeRows = (rows: UserTenantRoles[]): string[] =>
  rows.map((r) =>
    JSON.stringify({
      tenant_id: r.tenant_id,
      tenant_name: r.tenant_name ?? null,
      roles: r.roles,
    })
  )

/** 解码行；忽略未选择租户的空行，同一租户只保留最后一行。 */
export const decodeRows = (v: string[]): UserTenantRoles[] => {
  const m = new Map<string, UserTenantRoles>()
  for (const x of v) {
    const r = JSON.parse(x) as UserTenantRoles
    if (r.tenant_id)
      m.set(r.tenant_id, { tenant_id: r.tenant_id, roles: r.roles })
  }
  return [...m.values()]
}
