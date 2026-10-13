/** 以租户身份进入（超级用户模拟）的共享逻辑。 */
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/auth-store'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/api/client'

/**
 * 返回"进入租户"函数：先调用 POST /platform/tenants/{id}/enter（服务端记入平台操作日志），
 * 再把该租户设为当前租户（X-Tenant-ID）并跳转到工作区首页。
 */
export function useEnterTenant() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const setTenantId = useAuthStore((s) => s.setTenantId)
  const setImpersonating = useAuthStore((s) => s.setImpersonating)
  return async (tenant: { id: string; name: string }) => {
    try {
      await api.platform.enterTenant(tenant.id)
    } catch (e) {
      toast.error(errorMessage(e))
      return
    }
    setTenantId(tenant.id)
    setImpersonating(tenant)
    qc.invalidateQueries()
    navigate({ to: '/' })
  }
}
