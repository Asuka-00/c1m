/** PM 后 Qual 放行接口（后端 B6：`/mes/eqp/qual/{task_id}/result`，任务走通用实体 equipment_qual）。 */
import { http } from '../client'
import { BODY_KEYS, pickBody } from '../request-body'
import { mesApi } from './common'

/** 待登记的 Qual 任务（时间为带 Z 的 UTC）。 */
export interface QualTask {
  id: string
  equipment_id: string
  sub_unit_id: string | null
  sub_unit_label: string | null
  pm_plan_label: string | null
  requested_at: string | null
  qual_status: string
}

/** 登记 Qual 结果的返回。 */
export interface QualResultOut {
  data: QualTask
  next_task: QualTask | null
  equipment: { id: string; code: string; qual_state: string }
}

export const qualApi = {
  /** 所有打开的 Qual 任务（看板用来显示子单元与生成时间）。 */
  openTasks: () =>
    mesApi
      .list('equipment_qual', { qual_status: 'open', page_size: 100 })
      .then((r) =>
        (r.data as unknown as QualTask[]).filter(
          (x) => x.qual_status === 'open'
        )
      ),
  /** 登记结果：pass 放行；fail 保持待 Qual 并生成复测任务。请求体只含 result / comment。 */
  record: (
    taskId: string,
    body: { result: 'pass' | 'fail'; comment?: string }
  ) =>
    http
      .post<QualResultOut>(
        `/mes/eqp/qual/${taskId}/result`,
        pickBody(body, BODY_KEYS.qualResult)
      )
      .then((r) => r.data),
}
