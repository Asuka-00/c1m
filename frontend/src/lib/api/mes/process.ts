/** MES 工艺接口。 */
import { http } from '../client'
import type { MesRow } from './common'

/**
 * 按给定顺序重排路线工步（仅草稿路线）。
 *
 * @param routeId - 路线 id
 * @param ids - 全部工步 id 的新顺序
 */
export const reorderRouteSteps = (routeId: string, stepIds: string[]) =>
  http
    .post<{ data: MesRow[] }>(`/mes/route/${routeId}/reorder`, {
      step_ids: stepIds,
    })
    .then((r) => r.data)
