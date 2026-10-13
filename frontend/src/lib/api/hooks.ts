import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query'
import { useRouterState } from '@tanstack/react-router'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/auth-store'
import { isPlatformPath } from '../space'
import { errorMessage } from './client'
import { api } from './index'
import type { MenuNode, MenuSpace, MyTenant } from './types'

/** 查询 key 包含当前租户，切换租户时会重新获取。 */
export function useTenantKey() {
  return useAuthStore((s) => s.tenantId) ?? 'auto'
}

/** 当前登录用户。 */
export const useMe = () => useQuery({ queryKey: ['me'], queryFn: api.me })
/** 当前用户可访问的租户。 */
export const useMyTenants = () =>
  useQuery({ queryKey: ['tenants', 'me'], queryFn: api.myTenants })

/** 当前所在空间：`/platform/...` 为平台管理控制台，其余为租户工作区。 */
export function useSpace(): MenuSpace {
  const path = useRouterState({ select: (s) => s.location.pathname })
  return isPlatformPath(path) ? 'platform' : 'workspace'
}

/**
 * 当前用户的菜单树与权限（按空间与租户缓存）。
 *
 * @param space 菜单空间，默认取当前路由所在空间。
 */
export function useMyMenus(space?: MenuSpace) {
  const tk = useTenantKey()
  const current = useSpace()
  const sp = space ?? current
  return useQuery({
    queryKey: ['menus', 'me', sp, tk],
    queryFn: () => api.myMenus(sp),
  })
}

/**
 * 平台管理控制台入口路径：工作区菜单声明 platform_access 时，取平台菜单中第一个可访问的页面。
 *
 * @returns 入口路径；无平台权限（或正在模拟租户）时为 null
 */
export function usePlatformEntry(): string | null {
  const ws = useMyMenus('workspace')
  const allowed = !!ws.data?.platform_access
  const tk = useTenantKey()
  const pm = useQuery({
    queryKey: ['menus', 'me', 'platform', tk],
    queryFn: () => api.myMenus('platform'),
    enabled: allowed,
  })
  if (!allowed) return null
  const first = (ns: MenuNode[]): string | null => {
    for (const n of ns) {
      if (n.path) return n.path
      const c = first(n.children)
      if (c) return c
    }
    return null
  }
  return first(pm.data?.menus ?? []) ?? '/platform/tenants'
}

/** 实际生效的租户（用户所选，或后端解析出的租户）。 */
export function useCurrentTenant(): MyTenant | null {
  const menus = useMyMenus('workspace')
  const tenants = useMyTenants()
  const imp = useAuthStore((s) => s.impersonating)
  const id = menus.data?.tenant_id
  const found = tenants.data?.data.find((t) => t.tenant.id === id)
  if (found) return found
  // 以租户身份进入（非成员）：租户不在 /tenants/me 中，用模拟信息补齐
  if (imp && id && imp.id === id)
    return {
      tenant: {
        id,
        name: imp.name,
        slug: '',
        status: 'active',
        created_at: null,
      },
      roles: [],
      permissions: menus.data?.permissions ?? [],
    }
  return null
}

/**
 * 返回权限判断函数（基于 /menus/me 返回的权限，超级用户恒为 true）。
 *
 * @returns `(code: string) => boolean`
 */
export function useCan() {
  const { data } = useMyMenus()
  return (code: string) =>
    !!data && (data.is_superuser || data.permissions.includes(code))
}

/** 带提示消息的变更，并使给定前缀的查询失效。 */
export function useApiMutation<TVars, TRes>(
  fn: (v: TVars) => Promise<TRes>,
  invalidate: QueryKey[],
  success?: string
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k }))
      if (success) toast.success(success)
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
}
