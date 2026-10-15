import axios, { AxiosError } from 'axios'
import i18n, { currentLanguage, t } from '@/i18n'
import { useAuthStore } from '@/stores/auth-store'

/** 后端 API 地址（VITE_API_URL，默认 http://localhost:8000）。 */
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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
      (error.response?.data as { detail?: string })?.detail ===
        'Tenant not found' &&
      !url.startsWith('/tenants/')
    ) {
      useAuthStore.getState().setTenantId(null)
    }
    return Promise.reject(error)
  }
)

/** 把 API 错误转换为可读的多语言消息。已知的后端
 *  `detail` 字符串会被翻译（backend.<detail>）；否则回退为
 *  按状态码的翻译消息，最后才是原始 detail。 */
export function errorMessage(e: unknown): string {
  if (e instanceof AxiosError) {
    if (!e.response) return t('errors.network')
    const status = e.response.status
    const d = (e.response.data as { detail?: unknown })?.detail
    if (typeof d === 'string') {
      const key = `backend.${d}`
      return i18n.exists(key) ? t(key) : d
    }
    if (status === 422) {
      if (Array.isArray(d)) {
        const msgs = d.map((x: { msg?: string }) => x.msg).filter(Boolean)
        return `${t('errors.validation')} ${msgs.join(', ')}`.trim()
      }
      return t('errors.validation')
    }
    if (status === 403) return t('errors.forbidden')
    if (status >= 500) return t('errors.server')
    return e.message
  }
  return String(e)
}
