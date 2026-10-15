/** 检查结果卡片：显示预检 / 卡控结果，可在有权限时强制放行。 */
import { t } from '@/i18n'
import { ListChecks, SearchCheck } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/desc-list'
import { CheckPanel } from '../exec-parts'
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
      <CardHeader>
        <CardTitle className='flex items-center gap-2 text-base'>
          <ListChecks className='size-4 text-muted-foreground' />
          {t('mes.exec.checks')}
        </CardTitle>
      </CardHeader>
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
