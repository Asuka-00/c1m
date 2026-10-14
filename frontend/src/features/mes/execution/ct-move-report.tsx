/** P3 Cycle Time / Move 报表（D62 + D63）：按日期、工序、产品筛选，CT 趋势与 Move 数（柱）+ 按工序明细表。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTenantKey } from '@/lib/api/hooks'
import {
  CT_MOVE_MAX_DAYS,
  ctMoveApi,
  rangeProblem,
  type CtMoveOperationRow,
  type CtMoveTrendPoint,
} from '@/lib/api/mes/ct-move'
import { decimalText } from '@/lib/decimal'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/crud'
import { RefSelect } from '@/features/mes/common/ref-select'
import { ctMoveErrorMessage } from './ct-move-errors'
import { DataCard, DateRange, Kpi } from './report-parts'
import { isoDay } from './report-utils'

const hours = (v: unknown) =>
  v == null || v === '' ? '—' : decimalText(v as string)

/** CT（小时）折线 + Move 数柱状图。 */
export function CtMoveChart({ rows }: { rows: CtMoveTrendPoint[] }) {
  if (!rows.length)
    return (
      <p className='py-10 text-center text-sm text-muted-foreground'>
        {t('common.noResults')}
      </p>
    )
  const ct = t('mes.ctMove.ct')
  const mv = t('mes.ctMove.moves')
  const data = rows.map((r) => ({
    day: r.day.slice(5),
    [mv]: r.moves,
    [ct]: r.ct_avg_hours == null ? null : Number(r.ct_avg_hours),
  }))
  return (
    <div className='h-72' data-testid='ct-move-chart'>
      <ResponsiveContainer width='100%' height='100%'>
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray='3 3' className='stroke-muted' />
          <XAxis dataKey='day' fontSize={12} />
          <YAxis yAxisId='m' fontSize={12} allowDecimals={false} />
          <YAxis yAxisId='c' orientation='right' unit='h' fontSize={12} />
          <Tooltip
            formatter={(v, name) => [
              v == null ? '—' : String(v as number | string),
              name,
            ]}
          />
          <Legend />
          <Bar yAxisId='m' dataKey={mv} fill='#3b82f6' />
          <Line
            yAxisId='c'
            dataKey={ct}
            stroke='#f59e0b'
            dot
            connectNulls={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/** CT / Move 报表页。 */
export default function CtMoveReport() {
  const tk = useTenantKey()
  const [from, setFrom] = useState(isoDay(-13))
  const [to, setTo] = useState(isoDay())
  const [op, setOp] = useState<{ id: string | null; label: string | null }>({
    id: null,
    label: null,
  })
  const [prod, setProd] = useState<{ id: string | null; label: string | null }>(
    { id: null, label: null }
  )
  const problem = rangeProblem(from, to)
  const ok = problem == null
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'report-ct-move', from, to, op.id, prod.id],
    queryFn: () =>
      ctMoveApi.report({
        date_from: from,
        date_to: to,
        operation_id: op.id ?? undefined,
        product_id: prod.id ?? undefined,
      }),
    enabled: ok,
    retry: false,
  })
  const d = q.data
  return (
    <Page
      title={t('menu.mes-ct-move-report')}
      description={t('mes.ctMove.hint')}
    >
      <div className='flex flex-wrap items-end gap-3'>
        <DateRange from={from} to={to} setFrom={setFrom} setTo={setTo} />
        <div className='grid min-w-48 gap-1'>
          <Label htmlFor='ctm-op'>{t('mes.ctMove.operation')}</Label>
          <RefSelect
            id='ctm-op'
            target='operation'
            value={op.id}
            label={op.label}
            onChange={(id, label) => setOp({ id, label })}
          />
        </div>
        <div className='grid min-w-48 gap-1'>
          <Label htmlFor='ctm-prod'>{t('mes.ctMove.product')}</Label>
          <RefSelect
            id='ctm-prod'
            target='product'
            value={prod.id}
            label={prod.label}
            onChange={(id, label) => setProd({ id, label })}
          />
        </div>
        {d?.timezone && (
          <span
            className='text-xs text-muted-foreground'
            data-testid='ct-move-tz'
          >
            {t('mes.ctMove.timezone', { tz: d.timezone })}
          </span>
        )}
        {d?.mock && (
          <Badge variant='outline' data-testid='ct-move-mock'>
            {t('mes.ctMove.mock')}
          </Badge>
        )}
      </div>
      {problem && (
        <p className='text-sm text-destructive' data-testid='ct-move-range'>
          {problem === 'too_large'
            ? t('mes.err.code.date_range_too_large', {
                max_days: CT_MOVE_MAX_DAYS,
              })
            : problem === 'inverted'
              ? t('mes.err.code.range_inverted')
              : t('mes.ctMove.rangeInvalid')}
        </p>
      )}
      {ok && q.isError && (
        <p className='text-sm text-destructive' data-testid='ct-move-error'>
          {ctMoveErrorMessage(q.error)}
        </p>
      )}
      <div className='grid gap-3 sm:grid-cols-3 lg:grid-cols-5'>
        <Kpi label={t('mes.ctMove.moves')} value={d?.total.moves ?? '—'} />
        <Kpi
          label={t('mes.ctMove.moveQty')}
          value={d ? decimalText(d.total.move_qty) : '—'}
        />
        <Kpi
          label={t('mes.ctMove.reworkMoves')}
          value={
            d
              ? `${d.total.rework_moves} / ${decimalText(d.total.rework_move_qty)}`
              : '—'
          }
        />
        <Kpi
          label={t('mes.ctMove.ctAvg')}
          value={hours(d?.total.ct_avg_hours)}
        />
        <Kpi label={t('mes.ctMove.hold')} value={hours(d?.total.hold_hours)} />
      </div>
      <Card className='gap-3'>
        <CardHeader>
          <CardTitle className='text-base'>{t('mes.ctMove.trend')}</CardTitle>
        </CardHeader>
        <CardContent>
          <CtMoveChart rows={d?.trend ?? []} />
        </CardContent>
      </Card>
      <DataCard<CtMoveOperationRow>
        title={t('mes.ctMove.byOperation')}
        rows={d?.by_operation ?? []}
        max={100}
        exportName='ct-move'
        cols={[
          { head: t('mes.ctMove.operation'), get: (r) => r.operation },
          { head: t('mes.ctMove.name'), get: (r) => r.operation_name ?? '' },
          { head: t('mes.ctMove.moves'), get: (r) => r.moves, right: true },
          {
            head: t('mes.ctMove.moveQty'),
            get: (r) => decimalText(r.move_qty),
            right: true,
          },
          {
            head: t('mes.ctMove.reworkMoves'),
            get: (r) => `${r.rework_moves} / ${decimalText(r.rework_move_qty)}`,
            right: true,
          },
          {
            head: t('mes.ctMove.ctAvg'),
            get: (r) => hours(r.ct_avg_hours),
            right: true,
          },
          {
            head: t('mes.ctMove.ctP50'),
            get: (r) => hours(r.ct_p50_hours),
            right: true,
          },
          {
            head: t('mes.ctMove.ctP90'),
            get: (r) => hours(r.ct_p90_hours),
            right: true,
          },
          {
            head: t('mes.ctMove.hold'),
            get: (r) => hours(r.hold_hours),
            right: true,
          },
          { head: t('mes.ctMove.wip'), get: (r) => r.wip_lots, right: true },
          {
            head: t('mes.ctMove.onHold'),
            get: (r) => `${r.on_hold_lots} / ${decimalText(r.on_hold_qty)}`,
            right: true,
          },
        ]}
      />
    </Page>
  )
}
