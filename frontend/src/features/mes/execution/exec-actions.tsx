/** 执行模块的行操作与工具寿命组件。 */
import { Link } from '@tanstack/react-router'
import { t } from '@/i18n'
import { Gauge, History } from 'lucide-react'
import type { MesRow } from '@/lib/api/mes/common'
import { IconButton } from '@/components/icon-button'
import { lotPageLink } from './shared/lot-links'

/** 批次行操作：在操作台的作业 / 履历页签中打开。 */
export function LotActions({ row }: { row: MesRow }) {
  return (
    <>
      <IconButton label={t('menu.mes-lot-console')} variant='ghost' asChild>
        <Link {...lotPageLink(row.id)} aria-label={t('menu.mes-lot-console')}>
          <Gauge className='size-4' />
        </Link>
      </IconButton>
      <IconButton label={t('mes.lotView.history')} variant='ghost' asChild>
        <Link
          {...lotPageLink(row.id, 'history')}
          aria-label={t('mes.lotView.history')}
        >
          <History className='size-4' />
        </Link>
      </IconButton>
    </>
  )
}

/** 工具寿命条：已用 / 上限（按预警阈值着色）。 */
export function ToolLife({ row }: { row: MesRow }) {
  const used = Number(row.usage_count ?? 0)
  const max = Number(row.max_usage ?? 0)
  if (!max) return <span>{used}</span>
  const pct = Math.min(100, (used / max) * 100)
  const warn = pct >= Number(row.warn_pct ?? 90)
  return (
    <div className='flex min-w-28 items-center gap-2' title={`${used}/${max}`}>
      <div className='h-2 w-20 overflow-hidden rounded bg-muted'>
        <div
          className={
            pct >= 100
              ? 'h-full bg-destructive'
              : warn
                ? 'h-full bg-amber-500'
                : 'h-full bg-emerald-500'
          }
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className='text-xs tabular-nums'>
        {used}/{max}
      </span>
    </div>
  )
}
