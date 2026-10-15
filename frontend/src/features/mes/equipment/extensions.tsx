/** 设备模块：向通用实体页面注册的 UI 扩展（PM 计划到期状态列、上料记录卸料按钮、报警清除）。 */
import { t } from '@/i18n'
import type { MountRow } from '@/lib/api/mes/equipment'
import type { MesExtensions } from '@/features/mes/common/types'
import { AlarmClearButton } from './alarm-clear'
import { SkipReasonCell, StateChangedCell } from './alarm-columns'
import { MigrationNoteCell } from './migration-note'
import { UnmountButton } from './mount-dialog'
import { PmPlanStatus } from './pm-plan-status'

/** 设备模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  extraActions: {
    alarm_log: (r) => <AlarmClearButton row={r} />,
    equipment_material_mount: (r) => (
      <UnmountButton row={r as unknown as MountRow} />
    ),
  },
  extraColumns: {
    // baf7b55：报警履历的状态联动结果
    alarm_log: [
      {
        header: () => t('mes.alarm.col.stateChanged'),
        cell: (r) => <StateChangedCell row={r} />,
      },
      {
        header: () => t('mes.alarm.col.skipReason'),
        cell: (r) => <SkipReasonCell row={r} />,
      },
    ],
    // OQ-20：报警码「迁移待补配」
    alarm_code: [
      {
        header: () => t('mes.alarmCode.migration.col'),
        cell: (r) => <MigrationNoteCell row={r} />,
      },
    ],
    pm_plan: [
      {
        header: () => t('mes.pmStatus.title'),
        cell: (r) => <PmPlanStatus row={r} />,
      },
    ],
  },
}
