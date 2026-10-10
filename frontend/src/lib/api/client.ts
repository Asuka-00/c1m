import axios, { AxiosError } from 'axios'
import i18n, { currentLanguage, t } from '@/i18n'
import { useAuthStore } from '@/stores/auth-store'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/** Axios instance: attaches Bearer token + X-Tenant-ID; 401 -> logout. */
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
    // selected tenant vanished / no longer a member -> fall back to default resolution
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

/** Human-readable, translated error message for an API error. Known backend
 *  `detail` strings are translated (backend.<detail>); otherwise falls back to
 *  a translated message by status, then to the raw detail. */
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
