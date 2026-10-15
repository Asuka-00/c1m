/** 设备模块：向通用实体页面注册的 UI 扩展（PM 计划到期状态列）。 */
import { t } from '@/i18n'
import type { MesExtensions } from '@/features/mes/common/types'
import { PmPlanStatus } from './pm-plan-status'

/** 设备模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  extraColumns: {
    pm_plan: [
      {
        header: () => t('mes.pmStatus.title'),
        cell: (r) => <PmPlanStatus row={r} />,
      },
    ],
  },
}
