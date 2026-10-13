/** 以租户身份进入 / 退出（平台管理员模拟）的共享逻辑。 */
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/auth-store'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/api/client'

/**
 * 返回"进入租户"函数：调用 POST /platform/tenants/{id}/enter（服务端记入平台操作日志）
 * 取得绑定该租户的短期模拟令牌；保存原平台令牌后改用模拟令牌，跳转到工作区首页。
 */
export function useEnterTenant() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const start = useAuthStore((s) => s.startImpersonation)
  return async (tenant: { id: string; name: string }) => {
    let token: string
    try {
      token = (await api.platform.enterTenant(tenant.id)).access_token
    } catch (e) {
      toast.error(errorMessage(e))
      return
    }
    start({ id: tenant.id, name: tenant.name }, token)
    qc.clear()
    navigate({ to: '/' })
  }
}

/**
 * 返回"退出租户模拟"函数：恢复原平台令牌、记录退出日志并回到平台租户列表。
 *
 * @param toPlatform - 退出后是否跳转到平台租户列表（默认 true）
 */
export function useExitTenant(toPlatform = true) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const end = useAuthStore((s) => s.endImpersonation)
  return () => {
    const imp = end()
    qc.clear()
    if (imp) void api.platform.exitTenant(imp.id).catch(() => undefined)
    if (toPlatform)
      navigate({ to: '/$', params: { _splat: 'platform/tenants' } })
  }
}
