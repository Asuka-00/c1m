import { create } from 'zustand'

const TOKEN_KEY = 'fsft_token'
const TENANT_KEY = 'fsft_tenant'
const IMP_KEY = 'fsft_impersonating'

/** 超级用户"以租户身份进入"的目标租户。 */
interface Impersonation {
  id: string
  name: string
}

const loadImp = (): Impersonation | null => {
  try {
    return JSON.parse(localStorage.getItem(IMP_KEY) ?? 'null')
  } catch {
    return null
  }
}

interface AuthState {
  accessToken: string
  tenantId: string | null
  /** 正在以哪个租户身份查看（非成员租户，仅超级用户） */
  impersonating: Impersonation | null
  setImpersonating: (t: Impersonation | null) => void
  setAccessToken: (token: string) => void
  setTenantId: (tenantId: string | null) => void
  reset: () => void
}

/** 访问令牌 + 当前所选租户（作为 X-Tenant-ID 发送）。 */
export const useAuthStore = create<AuthState>()((set) => ({
  accessToken: localStorage.getItem(TOKEN_KEY) ?? '',
  tenantId: localStorage.getItem(TENANT_KEY),
  impersonating: loadImp(),
  setImpersonating: (impersonating) => {
    if (impersonating)
      localStorage.setItem(IMP_KEY, JSON.stringify(impersonating))
    else localStorage.removeItem(IMP_KEY)
    set({ impersonating })
  },
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
    localStorage.removeItem(IMP_KEY)
    set({ accessToken: '', tenantId: null, impersonating: null })
  },
}))
