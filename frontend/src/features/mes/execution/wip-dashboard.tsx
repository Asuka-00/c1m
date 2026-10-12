/** WIP 看板：在制分布、滞留批次、产出日报。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi } from '@/lib/api/mes/execution'
import { Badge } from '@/components/ui/badge'
import { Page } from '@/components/crud'
import { enumLabel } from '@/features/mes/common/labels'
import { DataCard, DateRange, Kpi } from './report-parts'
import { isoDay } from './report-utils'

/** WIP 看板页面。 */
export default function WipDashboard() {
  const tk = useTenantKey()
  const [from, setFrom] = useState(isoDay(-6))
  const [to, setTo] = useState(isoDay())
  const w = useQuery({
    queryKey: ['mes', 'exec', tk, 'report-wip'],
    queryFn: execApi.wip,
    refetchInterval: 60_000,
  })
  const o = useQuery({
    queryKey: ['mes', 'exec', tk, 'report-output', from, to],
    queryFn: () => execApi.output({ date_from: from, date_to: to }),
    enabled: !!from && !!to && from <= to,
  })
  const d = w.data
  const maxStep = Math.max(1, ...(d?.by_step ?? []).map((s) => s.qty))
  return (
    <Page
      title={t('menu.mes-wip-dashboard')}
      description={t('mes.report.hint')}
    >
      <div className='grid gap-4'>
        <div className='grid gap-4 sm:grid-cols-3'>
          <Kpi label={t('mes.report.lots')} value={d?.total_lots ?? '—'} />
          <Kpi label={t('mes.report.qty')} value={d?.total_qty ?? '—'} />
          <Kpi label={t('mes.report.onHold')} value={d?.on_hold ?? '—'} />
        </div>
        <div className='grid gap-4 lg:grid-cols-2'>
          <DataCard
            title={t('mes.report.byStep')}
            rows={d?.by_step ?? []}
            cols={[
              { head: t('mes.report.route'), get: (r) => r.route ?? '—' },
              { head: t('mes.report.step'), get: (r) => r.step_seq ?? '—' },
              {
                head: t('mes.report.operation'),
                get: (r) => r.operation ?? '—',
              },
              { head: t('mes.report.lots'), get: (r) => r.lots, right: true },
              {
                head: t('mes.report.qty'),
                right: true,
                get: (r) => (
                  <span className='inline-flex items-center justify-end gap-2'>
                    <span
                      className='h-2 rounded bg-primary/60'
                      style={{ width: `${(r.qty / maxStep) * 80}px` }}
                    />
                    {r.qty}
                  </span>
                ),
              },
              {
                head: t('mes.report.onHold'),
                get: (r) => r.on_hold,
                right: true,
              },
            ]}
          />
          <div className='grid gap-4'>
            <DataCard
              title={t('mes.report.byStatus')}
              rows={d?.by_status ?? []}
              cols={[
                {
                  head: t('mes.report.status'),
                  get: (r) => enumLabel('lot_status', r.status),
                },
                { head: t('mes.report.lots'), get: (r) => r.lots, right: true },
                { head: t('mes.report.qty'), get: (r) => r.qty, right: true },
              ]}
            />
            <DataCard
              title={t('mes.report.byProduct')}
              rows={d?.by_product ?? []}
              cols={[
                { head: t('mes.report.product'), get: (r) => r.product ?? '—' },
                { head: t('mes.report.lots'), get: (r) => r.lots, right: true },
                { head: t('mes.report.qty'), get: (r) => r.qty, right: true },
              ]}
            />
          </div>
        </div>
        <DataCard
          title={t('mes.report.aging')}
          rows={d?.aging ?? []}
          cols={[
            {
              head: t('mes.report.lot'),
              get: (r) => (
                <Link
                  to='/$'
                  params={{ _splat: 'mes/lot-console' }}
                  search={{ lot: r.id } as never}
                  className='font-mono underline-offset-2 hover:underline'
                >
                  {r.lot}
                </Link>
              ),
            },
            {
              head: t('mes.report.status'),
              get: (r) => (
                <span className='inline-flex gap-1'>
                  {enumLabel('lot_status', r.status)}
                  {r.on_hold && <Badge variant='destructive'>Hold</Badge>}
                </span>
              ),
            },
            { head: t('mes.report.step'), get: (r) => r.step_seq ?? '—' },
            { head: t('mes.report.qty'), get: (r) => r.qty, right: true },
            {
              head: t('mes.report.since'),
              get: (r) => (r.since ? fmtDateTime(r.since) : '—'),
            },
            {
              head: t('mes.report.hours'),
              get: (r) => r.hours ?? '—',
              right: true,
            },
          ]}
        />
        <div className='flex items-end justify-between'>
          <h3 className='font-semibold'>{t('mes.report.output')}</h3>
          <DateRange from={from} to={to} setFrom={setFrom} setTo={setTo} />
        </div>
        <DataCard
          title={t('mes.report.output')}
          rows={o.data ?? []}
          max={366}
          cols={[
            { head: t('mes.report.day'), get: (r) => r.day },
            { head: t('mes.report.moves'), get: (r) => r.moves, right: true },
            {
              head: t('mes.report.moveQty'),
              get: (r) => r.move_qty,
              right: true,
            },
            {
              head: t('mes.report.scrapQty'),
              get: (r) => r.scrap_qty,
              right: true,
            },
            {
              head: t('mes.report.completed'),
              get: (r) => r.completed,
              right: true,
            },
          ]}
        />
      </div>
    </Page>
  )
}
