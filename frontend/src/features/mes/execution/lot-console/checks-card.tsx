/** 检查结果卡片：显示预检 / 卡控结果，可在有权限时强制放行。 */
import { t } from '@/i18n'
import { ListChecks, SearchCheck } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/desc-list'
import { CheckPanel } from '../shared/exec-parts'
import { SideCardHeader } from '../shared/side-card-header'
import type { StageRun } from './use-stage-run'

export function ChecksCard({
  stageRun,
  canOverride,
}: {
  stageRun: StageRun
  canOverride: boolean
}) {
  const { results, blocked, run } = stageRun
  return (
    <Card className='gap-3'>
      <SideCardHeader icon={ListChecks} title={t('mes.exec.checks')} />
      <CardContent>
        {results ? (
          <CheckPanel
            results={results}
            blocked={blocked}
            canOverride={canOverride}
            busy={run.isPending}
            onOverride={(reason) => run.mutate({ override: reason })}
          />
        ) : (
          <EmptyState icon={SearchCheck}>{t('mes.exec.checksHint')}</EmptyState>
        )}
      </CardContent>
    </Card>
  )
}
