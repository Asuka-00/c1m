/** 登录后同步站点时区（D75）：会话 / 租户 site_tz > 厂区列表 > Asia/Taipei。 */
import { useEffect, useSyncExternalStore } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useCurrentTenant, useMyMenus } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import {
  getSiteTz,
  resolveSiteTz,
  sessionSiteTz,
  setSiteTz,
  subscribeSiteTz,
} from '@/lib/site-tz'

/** 当前站点时区（变化时重新渲染）。 */
export const useSiteTz = (): string =>
  useSyncExternalStore(subscribeSiteTz, getSiteTz, getSiteTz)

/** 在登录后布局里调用一次。 */
export function useSiteTzSync(): void {
  const tenant = useCurrentTenant()
  const menus = useMyMenus('workspace')
  const tid = tenant?.tenant.id ?? null
  const fromSession = sessionSiteTz(tenant, menus.data)
  const sites = useQuery({
    queryKey: ['site-tz', 'sites', tid],
    queryFn: () =>
      mesApi.list('site', {
        page: 1,
        page_size: 100,
        sort_by: 'code',
        sort_order: 'asc',
      }),
    enabled: !!tid && !fromSession,
    staleTime: 10 * 60_000,
    retry: false,
  })
  const tz = resolveSiteTz([tenant, menus.data], sites.data?.data)
  useEffect(() => {
    setSiteTz(tz)
  }, [tz])
}
