/** 租户角色页面。 */
import { RolesManager } from './roles-manager'

/** 当前租户的角色管理页面。 */
export default function TenantRolesPage() {
  return <RolesManager scope={'tenant'} />
}
