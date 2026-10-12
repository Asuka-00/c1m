import { useQuery } from '@tanstack/react-query'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes'

export function useMesMeta() {
  const tk = useTenantKey()
  return useQuery({
    queryKey: ['mes', 'meta', tk],
    queryFn: mesApi.meta,
    staleTime: 5 * 60_000,
  })
}

export function useMesEntity(code: string) {
  const q = useMesMeta()
  return { ...q, entity: q.data?.entities.find((e) => e.code === code) }
}
