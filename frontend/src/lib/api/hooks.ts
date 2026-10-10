import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/auth-store'
import { errorMessage } from './client'
import { api } from './index'

/** Query keys include the current tenant so switching tenants refetches. */
export function useTenantKey() {
  return useAuthStore((s) => s.tenantId) ?? 'auto'
}

export const useMe = () => useQuery({ queryKey: ['me'], queryFn: api.me })
export const useMyTenants = () =>
  useQuery({ queryKey: ['tenants', 'me'], queryFn: api.myTenants })
export function useMyMenus() {
  const tk = useTenantKey()
  return useQuery({ queryKey: ['menus', 'me', tk], queryFn: api.myMenus })
}

/** The tenant actually in effect (selected one, or what the backend resolved). */
export function useCurrentTenant() {
  const menus = useMyMenus()
  const tenants = useMyTenants()
  const id = menus.data?.tenant_id
  return tenants.data?.data.find((t) => t.tenant.id === id) ?? null
}

export function useCan() {
  const { data } = useMyMenus()
  return (code: string) =>
    !!data && (data.is_superuser || data.permissions.includes(code))
}

/** Mutation with toast + invalidation of the given query key prefixes. */
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
