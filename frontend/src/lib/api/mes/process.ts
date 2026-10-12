/** MES process endpoints. */
import { http } from '../client'
import type { MesRow } from './common'

export const reorderRouteSteps = (routeId: string, stepIds: string[]) =>
  http
    .post<{ data: MesRow[] }>(`/mes/route/${routeId}/reorder`, {
      step_ids: stepIds,
    })
    .then((r) => r.data)
