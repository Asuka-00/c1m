import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { API_URL } from '@/lib/api/client'

/** 登录页应显示其品牌的最近租户（?tenant=slug） */
export const BRAND_TENANT_KEY = 'brand_tenant'

/** 生效的品牌信息（应用名、Logo、favicon、强调色、页脚）。 */
export interface Branding {
  appName: string
  subtitle: string
  logo: string | null
  favicon: string | null
  loginBackground: string | null
  primaryColor: string | null
  footer: string
  supportUrl: string | null
}

/** 后端文件路径（/api/v1/files/..）-> API 主机上的绝对 URL */
export const assetUrl = (v: unknown): string | null =>
  typeof v === 'string' && v ? (v.startsWith('/') ? `${API_URL}${v}` : v) : null

const str = (v: unknown, fallback = '') =>
  typeof v === 'string' && v ? v : fallback

/** 公开品牌查询的 react-query key。 */
export const brandingQueryKey = (slug?: string | null) =>
  ['config', 'public', slug ?? ''] as const

/** 租户 slug 对应的有效公开品牌（无 slug 时为平台默认值）。 */
export function useBranding(slug?: string | null): Branding {
  const { data } = useQuery({
    queryKey: brandingQueryKey(slug),
    queryFn: () => api.config.public(slug ?? undefined),
    staleTime: 60_000,
  })
  const b = data?.branding ?? {}
  return {
    appName: str(b.app_name, 'FastAPI Admin'),
    subtitle: str(b.app_subtitle),
    logo: assetUrl(b.logo),
    favicon: assetUrl(b.favicon),
    loginBackground: assetUrl(b.login_background),
    primaryColor: str(b.primary_color) || null,
    footer: str(b.footer_copyright),
    supportUrl: str(b.support_url) || null,
  }
}

/** 记住登录页要显示其品牌的租户 slug。 */
export const rememberBrandTenant = (slug: string | null | undefined) => {
  if (slug) localStorage.setItem(BRAND_TENANT_KEY, slug)
}
/** 读取记住的租户 slug。 */
export const rememberedBrandTenant = () =>
  localStorage.getItem(BRAND_TENANT_KEY)
