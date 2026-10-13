/** 工作区 · 角色权限：为当前租户的角色分配租户作用域权限。 */
import { PermissionsView } from './index'

export default function TenantRolePermissionsPage() {
  return <PermissionsView scope='tenant' />
}
