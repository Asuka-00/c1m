import { create } from 'zustand'

const TOKEN_KEY = 'fsft_token'
const TENANT_KEY = 'fsft_tenant'
const IMP_KEY = 'fsft_impersonating'
const ORIG_KEY = 'fsft_orig_token'

/** 平台管理员"以租户身份进入"的目标租户。 */
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
  /** 进入租户前的原平台令牌（模拟期间保存，退出时恢复） */
  originalToken: string | null
  /** 开始模拟：保存原令牌，改用绑定租户的短期模拟令牌 */
  startImpersonation: (t: Impersonation, token: string) => void
  /** 结束模拟：恢复原令牌并清除租户；返回被退出的租户（无模拟时为 null） */
  endImpersonation: () => Impersonation | null
  setAccessToken: (token: string) => void
  setTenantId: (tenantId: string | null) => void
  reset: () => void
}

/** 访问令牌 + 当前所选租户（作为 X-Tenant-ID 发送）。 */
export const useAuthStore = create<AuthState>()((set, get) => ({
  accessToken: localStorage.getItem(TOKEN_KEY) ?? '',
  tenantId: localStorage.getItem(TENANT_KEY),
  impersonating: loadImp(),
  originalToken: localStorage.getItem(ORIG_KEY),
  startImpersonation: (imp, token) => {
    const { originalToken, accessToken } = get()
    const orig = originalToken ?? accessToken
    localStorage.setItem(ORIG_KEY, orig)
    localStorage.setItem(IMP_KEY, JSON.stringify(imp))
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(TENANT_KEY, imp.id)
    set({
      originalToken: orig,
      impersonating: imp,
      accessToken: token,
      tenantId: imp.id,
    })
  },
  endImpersonation: () => {
    const { originalToken, impersonating } = get()
    localStorage.removeItem(IMP_KEY)
    localStorage.removeItem(ORIG_KEY)
    localStorage.removeItem(TENANT_KEY)
    if (originalToken) localStorage.setItem(TOKEN_KEY, originalToken)
    set((s) => ({
      impersonating: null,
      originalToken: null,
      tenantId: null,
      accessToken: originalToken ?? s.accessToken,
    }))
    return impersonating
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
    localStorage.removeItem(ORIG_KEY)
    set({
      accessToken: '',
      tenantId: null,
      impersonating: null,
      originalToken: null,
    })
  },
}))
