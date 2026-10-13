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

/** 工程变更单接口：发布（生效时间已到则立即生效）、取消。 */
export const changeApi = {
  act: (id: string, action: 'release' | 'cancel') =>
    http
      .post<{ data: MesRow }>(`/mes/change-order/${id}/${action}`, {})
      .then((r) => r.data.data),
}
