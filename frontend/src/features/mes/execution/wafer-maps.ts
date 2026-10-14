/** 单位转换 / 按 bin 拆批共用：本批晶圆及其最新坐标图（404 = 没有坐标图）。 */
import { useMemo } from 'react'
import { AxiosError } from 'axios'
import { useQueries } from '@tanstack/react-query'
import type { ExecContext } from '@/lib/api/mes/execution'
import { mapApi } from '@/lib/api/mes/map'
import type { TrfWafer } from './transform-plan'

/**
 * @returns 未报废晶圆；`map` 为坐标图、null（没有）或 undefined（查询中 / 无权限等，以预览为准）
 */
export function useWaferMaps(cx: ExecContext, open: boolean): TrfWafer[] {
  const units = useMemo(
    () =>
      cx.units.filter(
        (u) => u.unit_kind === 'wafer' && u.status !== 'scrapped'
      ),
    [cx.units]
  )
  const maps = useQueries({
    queries: units.map((u) => ({
      queryKey: ['mes', 'map', 'substrate', u.code],
      queryFn: async () => {
        try {
          return await mapApi.bySubstrate(u.code)
        } catch (e) {
          if (e instanceof AxiosError && e.response?.status === 404) return null
          throw e
        }
      },
      enabled: open,
      retry: false,
    })),
  })
  return units.map((u, i) => {
    const q = maps[i]
    return { id: u.id, code: u.code, map: q?.isSuccess ? q.data : undefined }
  })
}
