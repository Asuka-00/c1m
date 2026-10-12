import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { API_URL } from '@/lib/api/client'

/** last tenant whose branding the sign-in page should show (?tenant=slug) */
export const BRAND_TENANT_KEY = 'brand_tenant'

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

/** backend file paths (/api/v1/files/..) -> absolute URL on the API host */
export const assetUrl = (v: unknown): string | null =>
  typeof v === 'string' && v ? (v.startsWith('/') ? `${API_URL}${v}` : v) : null

const str = (v: unknown, fallback = '') =>
  typeof v === 'string' && v ? v : fallback

export const brandingQueryKey = (slug?: string | null) =>
  ['config', 'public', slug ?? ''] as const

/** Effective public branding for a tenant slug (platform defaults without one). */
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

export const rememberBrandTenant = (slug: string | null | undefined) => {
  if (slug) localStorage.setItem(BRAND_TENANT_KEY, slug)
}
export const rememberedBrandTenant = () =>
  localStorage.getItem(BRAND_TENANT_KEY)
