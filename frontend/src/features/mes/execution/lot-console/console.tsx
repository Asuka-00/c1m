/** 批次操作台主体：左侧概要与作业面板，右侧检查、Hold、拆合批与在制调整卡片。 */
import type { ExecContext } from '@/lib/api/mes/execution'
import { SplitMergeCard } from '../split-merge'
import { WipActionsCard } from '../wip-actions'
import { ActionPanel } from './action-panel'
import { ChecksCard } from './checks-card'
import { HoldCard } from './hold-card'
import { LotSummaryCard } from './lot-summary-card'
import { useStageForm } from './use-stage-form'
import { useStageRun } from './use-stage-run'

export function Console({ cx, perms }: { cx: ExecContext; perms: string[] }) {
  const form = useStageForm(cx)
  const stageRun = useStageRun(cx, form.body)
  const terminal = !cx.next_stage
  const onHold = !!cx.lot.on_hold
  const canRun = perms.includes('mes.exec:write') && !terminal && !onHold
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
          canOverride={perms.includes('mes.exec:override')}
        />
        <HoldCard cx={cx} perms={perms} />
        <SplitMergeCard cx={cx} perms={perms} />
        <WipActionsCard cx={cx} perms={perms} />
      </div>
    </div>
  )
}
