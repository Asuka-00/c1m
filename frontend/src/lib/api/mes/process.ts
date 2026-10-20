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

/** 画布上一个工步的节点坐标：工步节点 `x / y`，其子路线节点 `ax / ay`、返工路线节点 `rx / ry`。 */
export interface StepLayout {
  x: number
  y: number
  ax?: number
  ay?: number
  rx?: number
  ry?: number
}

/**
 * 保存画布节点位置（仅草稿路线）。
 *
 * @param routeId - 路线 id
 * @param steps - 工步 id -> 坐标；null 清除该工步已存的位置
 */
export const saveRouteLayout = (
  routeId: string,
  steps: Record<string, StepLayout | null>
) =>
  http
    .put<{ data: { saved: number } }>(`/mes/route/${routeId}/layout`, { steps })
    .then((r) => r.data.data)

/** 工程变更单接口：发布（生效时间已到则立即生效）、取消。 */
export const changeApi = {
  act: (id: string, action: 'release' | 'cancel') =>
    http
      .post<{ data: MesRow }>(`/mes/change-order/${id}/${action}`, {})
      .then((r) => r.data.data),
}
