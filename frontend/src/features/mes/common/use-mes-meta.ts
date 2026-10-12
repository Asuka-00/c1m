/** MES 元数据查询 Hook。 */
import { useQuery } from '@tanstack/react-query'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'

/** MES 元数据（`GET /mes/_meta`，按租户缓存）。 */
export function useMesMeta() {
  const tk = useTenantKey()
  return useQuery({
    queryKey: ['mes', 'meta', tk],
    queryFn: mesApi.meta,
    staleTime: 5 * 60_000,
  })
}

/** 按编码获取单个实体的元数据。 */
export function useMesEntity(code: string) {
  const q = useMesMeta()
  return { ...q, entity: q.data?.entities.find((e) => e.code === code) }
}
