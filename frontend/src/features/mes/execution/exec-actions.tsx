/** 执行模块的行操作与工具寿命组件。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { t } from '@/i18n'
import { Gauge, History, PlayCircle } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { decimalText } from '@/lib/decimal'
import { cn } from '@/lib/utils'
import { IconButton } from '@/components/icon-button'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { ReleaseDialog } from './lot-console/release-dialog'
import { lotPageLink } from './lot-links'
import { toolLifeLevel, warnRatio } from './tool-life'

/** 批次行操作：在操作台 / 履历时间线中打开。 */
export function LotActions({ row }: { row: MesRow }) {
  return (
    <>
      <IconButton label={t('menu.mes-lot-console')} variant='ghost' asChild>
        <Link
          {...lotPageLink('lot-console', row.id)}
          aria-label={t('menu.mes-lot-console')}
        >
          <Gauge className='size-4' />
        </Link>
      </IconButton>
      <IconButton label={t('menu.mes-lot-trace')} variant='ghost' asChild>
        <Link
          {...lotPageLink('lot-trace', row.id)}
          aria-label={t('menu.mes-lot-trace')}
        >
          <History className='size-4' />
        </Link>
      </IconButton>
    </>
  )
}

/** Hold 管理行操作：释放生效中的 Hold。 */
export function HoldActions({ row }: { row: MesRow }) {
  const [open, setOpen] = useState(false)
  const tk = useTenantKey()
  const can = useMesCan()
  const reasons = useQuery({
    queryKey: ['mes', 'reason_code', 'release', tk],
    queryFn: () =>
      mesApi.list('reason_code', { reason_type: 'release', page_size: 100 }),
    enabled: open,
  })
  return (
    <>
      <IconButton label={t('menu.mes-lot-console')} variant='ghost' asChild>
        <Link
          {...lotPageLink('lot-console', row.lot_id)}
          aria-label={t('menu.mes-lot-console')}
        >
          <Gauge className='size-4' />
        </Link>
      </IconButton>
      {row.is_active && can(MES_PERM.execHold) ? (
        <IconButton
          label={t('mes.exec.release')}
          variant='ghost'
          onClick={() => setOpen(true)}
        >
          <PlayCircle className='size-4' />
        </IconButton>
      ) : null}
      <ReleaseDialog
        hold={row}
        reasons={(reasons.data?.data ?? []).map((r) => ({
          id: r.id,
          code: String(r.code),
          name: String(r.name ?? ''),
        }))}
        open={open}
        onOpenChange={setOpen}
      />
    </>
  )
}

/** 工具寿命条：已用 / 上限（定点字符串原样显示；预警区间黄、达到上限红）。 */
export function ToolLife({ row }: { row: MesRow }) {
  const used = decimalText(row.usage_count as string) || '0'
  const max = decimalText(row.max_usage as string)
  const level = toolLifeLevel(used, max, warnRatio(row))
  if (!level) return <span className='tabular-nums'>{used}</span>
  const pct = Math.min(100, (Number(used) / Number(max)) * 100)
  const hint =
    level === 'over'
      ? t('mes.toolLife.over')
      : level === 'warn'
        ? t('mes.toolLife.warn')
        : ''
  return (
    <div
      className='flex min-w-28 items-center gap-2'
      title={`${used}/${max}${hint ? ` · ${hint}` : ''}`}
      data-testid='tool-life'
      data-level={level}
    >
      <div className='h-2 w-20 overflow-hidden rounded bg-muted'>
        <div
          className={
            level === 'over'
              ? 'h-full bg-destructive'
              : level === 'warn'
                ? 'h-full bg-amber-500'
                : 'h-full bg-emerald-500'
          }
          style={{ width: `${pct}%` }}
        />
      </div>
      <span
        className={cn(
          'text-xs tabular-nums',
          level === 'over' && 'text-destructive',
          level === 'warn' && 'text-amber-700 dark:text-amber-400'
        )}
      >
        {used}/{max}
      </span>
      {hint && <span className='sr-only'>{hint}</span>}
    </div>
  )
}
