import axios, { AxiosError } from 'axios'
import { currentLanguage, t } from '@/i18n'
import { useAuthStore } from '@/stores/auth-store'
import {
  codeText,
  detailParams,
  itemText,
  type CodedItem,
} from '@/lib/backend-text'
import { ErrorCode } from '@/lib/error-codes'

/** 后端 API 地址（VITE_API_URL；设为空字符串时使用同源，生产经 nginx 反代 /api；未设置时默认 http://localhost:8000）。 */
export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/** Axios 实例：附带 Bearer 令牌与 X-Tenant-ID；401 时登出。 */
export const http = axios.create({ baseURL: `${API_URL}/api/v1` })

http.interceptors.request.use((config) => {
  const { accessToken, tenantId } = useAuthStore.getState()
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  if (tenantId) config.headers['X-Tenant-ID'] = tenantId
  config.headers['Accept-Language'] = currentLanguage()
  return config
})

http.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    const status = error.response?.status
    const url = error.config?.url ?? ''
    const detailCode = codeOf(error.response?.data)
    const st = useAuthStore.getState()
    // 模拟令牌过期 / 失效：恢复原平台令牌并回到平台租户列表，而不是登出
    if (
      st.originalToken &&
      (status === 401 ||
        detailCode === ErrorCode.COULD_NOT_VALIDATE_CREDENTIALS)
    ) {
      st.endImpersonation()
      window.location.assign('/platform/tenants')
      return Promise.reject(error)
    }
    if (status === 401 || (status === 403 && url.includes('/users/me'))) {
      useAuthStore.getState().reset()
      if (!window.location.pathname.startsWith('/sign-in')) {
        const redirect = encodeURIComponent(window.location.pathname)
        window.location.assign(`/sign-in?redirect=${redirect}`)
      }
    }
    // 所选租户已不存在 / 已非成员 -> 回退到默认租户解析
    if (
      status === 404 &&
      detailCode === ErrorCode.TENANT_NOT_FOUND &&
      !url.startsWith('/tenants/')
    ) {
      useAuthStore.getState().setTenantId(null)
    }
    return Promise.reject(error)
  }
)

/** 响应体里的数字错误码（`detail.code`），没有时为 undefined。 */
function codeOf(data: unknown): number | undefined {
  const d = (data as { detail?: { code?: unknown } } | undefined)?.detail
  return typeof d?.code === 'number' ? d.code : undefined
}

/**
 * 把接口错误转换为当前语言的提示文本：数字错误码按 `error.code_<code>`（插值取 `params`）翻译；
 * 422 字段错误逐项翻译；框架级错误按状态码给通用提示。后端的英文原文不会直接显示。
 */
export function errorMessage(e: unknown): string {
  if (e instanceof AxiosError) {
    if (!e.response) return t('error.network')
    const status = e.response.status
    const d = (e.response.data as { detail?: unknown })?.detail
    if (d && typeof d === 'object' && !Array.isArray(d) && 'code' in d) {
      const coded = codeText(
        (d as { code?: unknown }).code,
        detailParams(d as Record<string, unknown>)
      )
      if (coded) return coded
    }
    if (status === 422) {
      if (Array.isArray(d)) {
        const msgs = d
          .map((x: CodedItem) => itemText(x) ?? x.msg)
          .filter(Boolean)
        return `${t('error.validation')} ${msgs.join(', ')}`.trim()
      }
      return t('error.validation')
    }
    // 框架级错误（路由不存在、方法不允许等，detail 为英文字符串）和未登记的错误码：按状态码给通用提示
    if (status === 403) return t('error.forbidden')
    if (status >= 500) return t('error.server')
    return t('error.generic')
  }
  return String(e)
}
