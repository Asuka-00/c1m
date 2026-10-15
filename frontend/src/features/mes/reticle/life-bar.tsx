/** 光罩寿命条（P3-F3）：绿 / 黄（预警区间）/ 红（达上限），悬停说明预警线和进站影响。 */
import { t } from '@/i18n'
import type { Reticle } from '@/lib/api/mes/reticle'
import { decimalText, mulDecimal } from '@/lib/decimal'
import { cn } from '@/lib/utils'
import { lifeRatio, reticleLifeLevel, reticleWarnRatio } from './reticle-rules'

const TONE = {
  ok: 'bg-emerald-500',
  warn: 'bg-amber-400',
  over: 'bg-destructive',
} as const

export function ReticleLifeBar({
  reticle: r,
  className,
}: {
  reticle: Pick<
    Reticle,
    'shot_count' | 'max_shots' | 'warn_ratio' | 'life_state'
  >
  className?: string
}) {
  const level = reticleLifeLevel(r)
  const used = decimalText(r.shot_count) || '0'
  if (level == null)
    return (
      <span
        className={cn('text-sm', className)}
        title={t('mes.reticle.life.noLimitTip')}
        data-testid='reticle-life'
        data-level='none'
      >
        {used} / —
      </span>
    )
  const max = decimalText(r.max_shots as string)
  const ratio = reticleWarnRatio(r)
  const tip = [
    t('mes.reticle.life.tip', {
      used,
      max,
      line: mulDecimal(max, ratio) ?? '—',
      pct: mulDecimal(ratio, 100) ?? '—',
    }),
    t(`mes.reticle.life.${level}Tip`),
  ].join('\n')
  const pct = Math.min(1, Math.max(0, lifeRatio(r) ?? 0)) * 100
  return (
    <div
      className={cn('flex min-w-36 flex-col gap-1', className)}
      title={tip}
      aria-label={tip}
      data-testid='reticle-life'
      data-level={level}
    >
      <span
        className={cn(
          'text-sm',
          level === 'over' && 'text-destructive',
          level === 'warn' && 'text-amber-600'
        )}
      >
        {used} / {max}
        {level !== 'ok' && ` · ${t(`mes.reticle.life.${level}`)}`}
      </span>
      <div className='h-1.5 w-full rounded bg-muted'>
        <div
          className={cn('h-1.5 rounded', TONE[level])}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
