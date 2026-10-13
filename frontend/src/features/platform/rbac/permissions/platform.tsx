/** 平台控制台 · 权限：平台角色的权限树与权限定义维护（仅超级用户）。 */
import { PermissionsView } from './index'

export default function PlatformPermissionsPage() {
  return <PermissionsView scope='platform' />
}
