import { create } from 'zustand'

const TOKEN_KEY = 'fsft_token'
const TENANT_KEY = 'fsft_tenant'

interface AuthState {
  accessToken: string
  tenantId: string | null
  setAccessToken: (token: string) => void
  setTenantId: (tenantId: string | null) => void
  reset: () => void
}

/** 访问令牌 + 当前所选租户（作为 X-Tenant-ID 发送）。 */
export const useAuthStore = create<AuthState>()((set) => ({
  accessToken: localStorage.getItem(TOKEN_KEY) ?? '',
  tenantId: localStorage.getItem(TENANT_KEY),
  setAccessToken: (accessToken) => {
    localStorage.setItem(TOKEN_KEY, accessToken)
    set({ accessToken })
  },
  setTenantId: (tenantId) => {
    if (tenantId) localStorage.setItem(TENANT_KEY, tenantId)
    else localStorage.removeItem(TENANT_KEY)
    set({ tenantId })
  },
  reset: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(TENANT_KEY)
    set({ accessToken: '', tenantId: null })
  },
}))
