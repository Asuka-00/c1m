/** 良率统计页面：按工序 / 产品 / 批次统计良率，报废原因帕累托。 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi, type YieldGroup } from '@/lib/api/mes/execution'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DataTable,
  Page,
  clientList,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { ParetoChart } from './pareto-chart'
import { DateRange } from './report-parts'
import { isoDay, pct } from './report-utils'

const GROUPS: YieldGroup[] = ['operation', 'product', 'lot']

/** 良率统计。 */
export default function YieldReport() {
  const tk = useTenantKey()
  const [from, setFrom] = useState(isoDay(-29))
  const [to, setTo] = useState(isoDay())
  const [group, setGroup] = useState<YieldGroup>('operation')
  const ok = !!from && !!to && from <= to
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'report-yield', from, to, group],
    queryFn: () => execApi.yieldReport({ date_from: from, date_to: to, group }),
    enabled: ok,
  })
  const all = useMemo(() => q.data?.rows ?? [], [q.data])
  const filters: FilterDef[] = [
    { type: 'text', name: 'q', placeholder: t('mes.yield.search') },
    {
      type: 'select',
      name: 'band',
      label: t('mes.yield.allBands'),
      options: (['low', 'mid', 'high'] as const).map((v) => ({
        value: v,
        label: t(`mes.yield.band.${v}`),
      })),
    },
  ]
  const lp = useListParams(filters)
  const view = clientList(all, lp, {
    text: (r) => `${r.key} ${r.name}`,
    match: {
      band: (r, v) => {
        const y = r.yield ?? 1
        return v === 'low'
          ? y < 0.9
          : v === 'mid'
            ? y >= 0.9 && y < 0.98
            : y >= 0.98
      },
    },
  })
  const tot = q.data?.total
  return (
    <Page title={t('menu.mes-yield-report')} description={t('mes.yield.hint')}>
      <div className='flex flex-wrap items-end gap-3'>
        <DateRange
          from={from}
          to={to}
          setFrom={setFrom}
          setTo={setTo}
          error={q.error}
        />
        <Select value={group} onValueChange={(v) => setGroup(v as YieldGroup)}>
          <SelectTrigger
            className='max-w-72 min-w-40'
            data-testid='yield-group'
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {GROUPS.map((g) => (
              <SelectItem key={g} value={g}>
                {t(`mes.yield.by.${g}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {tot && (
          <span className='text-sm text-muted-foreground'>
            {t('mes.yield.total', {
              good: tot.good,
              scrap: tot.scrap,
              y: pct(tot.yield),
            })}
          </span>
        )}
      </div>
      <Card className='gap-3'>
        <CardHeader>
          <CardTitle className='text-base'>{t('mes.yield.pareto')}</CardTitle>
        </CardHeader>
        <CardContent>
          <ParetoChart rows={q.data?.pareto ?? []} />
        </CardContent>
      </Card>
      <DataTable
        rows={view.rows}
        total={view.total}
        params={lp}
        filters={filters}
        loading={q.isLoading}
        rowKey={(r) => r.key}
        columns={[
          {
            header: t(`mes.yield.by.${group}`),
            sortKey: 'key',
            cell: (r) => <span className='font-mono'>{r.key}</span>,
          },
          { header: t('mes.yield.name'), cell: (r) => r.name },
          {
            header: t('mes.yield.good'),
            sortKey: 'good',
            className: 'text-right tabular-nums',
            cell: (r) => r.good,
          },
          {
            header: t('mes.yield.scrap'),
            sortKey: 'scrap',
            className: 'text-right tabular-nums',
            cell: (r) => r.scrap,
          },
          {
            header: t('mes.yield.yield'),
            sortKey: 'yield',
            className: 'text-right tabular-nums',
            cell: (r) => (
              <span
                className={
                  (r.yield ?? 1) < 0.9 ? 'font-medium text-red-600' : undefined
                }
              >
                {pct(r.yield)}
              </span>
            ),
          },
        ]}
      />
    </Page>
  )
}
