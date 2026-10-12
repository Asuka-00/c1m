import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { t } from '@/i18n'
import { Gauge, History, PlayCircle } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { Button } from '@/components/ui/button'
import { useMesMeta } from '@/features/mes/common/use-mes-meta'
import { ReleaseDialog } from './lot-console'

const pageLink = (page: string, lot: unknown) => ({
  to: '/$' as const,
  params: { _splat: `mes/${page}` },
  search: { lot: String(lot) } as never,
})

/** Lot row actions: open in the operation console / history timeline. */
export function LotActions({ row }: { row: MesRow }) {
  return (
    <>
      <Button
        size='icon'
        variant='ghost'
        asChild
        title={t('menu.mes-lot-console')}
      >
        <Link
          {...pageLink('lot-console', row.id)}
          aria-label={t('menu.mes-lot-console')}
        >
          <Gauge className='size-4' />
        </Link>
      </Button>
      <Button
        size='icon'
        variant='ghost'
        asChild
        title={t('menu.mes-lot-trace')}
      >
        <Link
          {...pageLink('lot-trace', row.id)}
          aria-label={t('menu.mes-lot-trace')}
        >
          <History className='size-4' />
        </Link>
      </Button>
    </>
  )
}

/** Hold management row action: release an active hold. */
export function HoldActions({ row }: { row: MesRow }) {
  const [open, setOpen] = useState(false)
  const tk = useTenantKey()
  const { data: meta } = useMesMeta()
  const reasons = useQuery({
    queryKey: ['mes', 'reason_code', 'release', tk],
    queryFn: () =>
      mesApi.list('reason_code', { reason_type: 'release', page_size: 100 }),
    enabled: open,
  })
  return (
    <>
      <Button
        size='icon'
        variant='ghost'
        asChild
        title={t('menu.mes-lot-console')}
      >
        <Link
          {...pageLink('lot-console', row.lot_id)}
          aria-label={t('menu.mes-lot-console')}
        >
          <Gauge className='size-4' />
        </Link>
      </Button>
      {row.is_active && meta?.perms.includes('mes.exec:hold') ? (
        <Button
          size='icon'
          variant='ghost'
          title={t('mes.exec.release')}
          aria-label={t('mes.exec.release')}
          onClick={() => setOpen(true)}
        >
          <PlayCircle className='size-4' />
        </Button>
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

/** Tool life bar: usage / max (warn threshold colours). */
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
