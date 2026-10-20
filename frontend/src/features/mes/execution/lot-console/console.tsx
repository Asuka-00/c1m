/** 批次操作台主体：左侧概要与作业面板，右侧检查、Hold、拆合批与在制调整卡片。 */
import type { ExecContext } from '@/lib/api/mes/execution'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { WipActionsCard } from '../dispatch/wip-actions'
import { canRunStage } from '../shared/lot-rules'
import { SplitMergeCard } from '../split-merge'
import { ActionPanel } from './action-panel'
import { ChecksCard } from './checks-card'
import { HoldCard } from './hold-card'
import { LotSummaryCard } from './lot-summary-card'
import { useStageForm } from './use-stage-form'
import { useStageRun } from './use-stage-run'

export function Console({ cx }: { cx: ExecContext }) {
  const can = useMesCan()
  const form = useStageForm(cx)
  const stageRun = useStageRun(cx, form.body)
  const canRun = can(MES_PERM.execWrite) && canRunStage(cx.lot, cx.next_stage)
  return (
    <div
      className='grid items-start gap-4 min-[1100px]:grid-cols-[minmax(0,1fr)_minmax(320px,380px)]'
      data-testid='console'
    >
      <div className='min-w-0 space-y-4'>
        <LotSummaryCard cx={cx} />
        <ActionPanel cx={cx} form={form} stageRun={stageRun} canRun={canRun} />
      </div>

      <div className='min-w-0 space-y-4'>
        <ChecksCard
          stageRun={stageRun}
          canOverride={can(MES_PERM.execOverride)}
        />
        <HoldCard cx={cx} />
        <SplitMergeCard cx={cx} />
        <WipActionsCard cx={cx} />
      </div>
    </div>
  )
}
