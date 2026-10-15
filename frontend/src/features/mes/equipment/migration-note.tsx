/** 报警码「迁移待补配」标记（OQ-20：0029 把无 UDT 的 hold_* 改成 none 时写入 `migration_note`）。 */
import { t } from '@/i18n'
import type { MesRow } from '@/lib/api/mes/common'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

/** 有迁移说明时显示标记，悬停看说明原文；没有显示「—」。 */
export function MigrationNoteCell({ row }: { row: MesRow }) {
  const note = row.migration_note
  if (note == null || note === '')
    return <span className='text-muted-foreground'>—</span>
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant='outline'
          className='border-amber-500 text-amber-700 dark:text-amber-400'
          title={String(note)}
          data-testid='migration-note'
        >
          {t('mes.alarmCode.migration.pending')}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className='max-w-xs'>
        <p>{t('mes.alarmCode.migration.hint')}</p>
        <p className='font-mono text-xs'>{String(note)}</p>
      </TooltipContent>
    </Tooltip>
  )
}
