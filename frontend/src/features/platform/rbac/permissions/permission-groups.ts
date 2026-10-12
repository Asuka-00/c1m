/** 权限分组工具。 */
import type { Permission } from '@/lib/api'

/** 权限树的资源分组节点。 */
export interface TreeGroup {
  resource: string
  perms: Permission[]
}

/** 按资源前缀对权限编码分组："users:read" -> users。 */
export function groupPermissions(perms: Permission[]): TreeGroup[] {
  const m = new Map<string, Permission[]>()
  for (const p of perms) {
    const res = p.code.includes(':') ? p.code.split(':')[0]! : 'other'
    m.set(res, [...(m.get(res) ?? []), p])
  }
  return [...m.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([resource, ps]) => ({
      resource,
      perms: ps.sort((a, b) => a.code.localeCompare(b.code)),
    }))
}
