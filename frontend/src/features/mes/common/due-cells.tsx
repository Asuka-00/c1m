/** 到期 / 时长类单元格：交期、有效期、停机持续时长。 */
import { useState } from 'react'
import { fmtDate, fmtDateTime, t } from '@/i18n'
import type { MesRow } from '@/lib/api/mes/common'
import { useSiteTz } from '@/lib/site-tz-sync'
import { Badge } from '@/components/ui/badge'
import { daysUntil } from './due'

/** 到期日单元格：已过期红色徽标，临近到期黄色。 */
export function DueCell({
  date,
  done = false,
  warnDays,
  overLabel,
  warnLabel,
}: {
  date: string | null
  done?: boolean
  warnDays: number
  overLabel: string
  warnLabel?: string
}) {
  // 站点时区变化时重新计算（D75）
  const tz = useSiteTz()
  if (!date) return <span className='text-muted-foreground'>—</span>
  const n = daysUntil(date, new Date(), tz)
  const text = fmtDate(date)
  if (done || n > warnDays) return <>{text}</>
  if (n < 0)
    return (
      <span className='inline-flex items-center gap-1 text-destructive'>
        {text}
        <Badge variant='destructive'>{overLabel}</Badge>
      </span>
    )
  return (
    <span className='inline-flex items-center gap-1 text-amber-600'>
      {text}
      {warnLabel && (
        <Badge className='bg-amber-500 text-white'>{warnLabel}</Badge>
      )}
    </span>
  )
}

/** 停机结束时间 + 持续时长（小时）；未结束显示“进行中”。 */
export function DowntimeEnd({ row }: { row: MesRow }) {
  // 渲染时刻作为未结束停机的“当前时间”
  const [now] = useState(() => Date.now())
  const start = Date.parse(String(row.start_at))
  const end = row.end_at ? Date.parse(String(row.end_at)) : now
  const h = ((end - start) / 3_600_000).toFixed(1)
  if (!row.end_at)
    return (
      <span className='inline-flex items-center gap-1'>
        <Badge variant='destructive'>{t('mes.due.ongoing')}</Badge>
        <span className='text-destructive tabular-nums'>
          {t('mes.due.hours', { n: h })}
        </span>
      </span>
    )
  return (
    <span className='inline-flex items-center gap-1'>
      {fmtDateTime(String(row.end_at))}
      <span className='text-muted-foreground tabular-nums'>
        ({t('mes.due.hours', { n: h })})
      </span>
    </span>
  )
}

/** Hold 时间 + 生效中 Hold 的已持续时长（小时）。 */
export function HeldAt({ row }: { row: MesRow }) {
  const [now] = useState(() => Date.now())
  if (!row.held_at) return <>—</>
  const h = ((now - Date.parse(String(row.held_at))) / 3_600_000).toFixed(1)
  return (
    <span className='inline-flex items-center gap-1'>
      {fmtDateTime(String(row.held_at))}
      {!!row.is_active && (
        <span className='text-amber-600 tabular-nums'>
          ({t('mes.due.hours', { n: h })})
        </span>
      )}
    </span>
  )
}
