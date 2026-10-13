/** 设备 OEE 报表：时间稼动率 × 性能稼动率 × 良品率（缺 UPH 不计算性能与 OEE）。 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi } from '@/lib/api/mes/execution'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Page } from '@/components/crud'
import { DataCard, DateRange } from './report-parts'
import { isoDay, pct } from './report-utils'

/** “全部工作中心”的选择值。 */
const ALL = '__all'

/** 设备 OEE 页面：日期区间 + 工作中心 / 设备关键字筛选、日趋势图、明细导出。 */
export default function OeeReport() {
  const tk = useTenantKey()
  const [from, setFrom] = useState(isoDay(-6))
  const [to, setTo] = useState(isoDay())
  const [wc, setWc] = useState(ALL)
  const [kw, setKw] = useState('')
  const ok = !!from && !!to && from <= to
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'report-oee', from, to],
    queryFn: () => execApi.oee({ date_from: from, date_to: to }),
    enabled: ok,
  })
  const trend = useQuery({
    queryKey: ['mes', 'exec', tk, 'report-oee-trend', from, to, wc],
    queryFn: () =>
      execApi.oeeTrend({
        date_from: from,
        date_to: to,
        workcenter: wc === ALL ? undefined : wc,
      }),
    enabled: ok,
  })
  const all = useMemo(() => q.data ?? [], [q.data])
  const wcs = [...new Set(all.map((r) => r.workcenter).filter(Boolean))]
    .sort()
    .map(String)
  const rows = all.filter(
    (r) =>
      (wc === ALL || r.workcenter === wc) &&
      `${r.equipment} ${r.name}`.toLowerCase().includes(kw.toLowerCase())
  )
  const chart = (trend.data ?? []).map((d) => ({
    day: d.day.slice(5),
    [t('mes.report.availability')]: d.availability && d.availability * 100,
    [t('mes.report.quality')]: d.quality && d.quality * 100,
    [t('mes.report.oee')]: d.oee && d.oee * 100,
  }))
  return (
    <Page
      title={t('menu.mes-oee-report')}
      description={t('mes.report.oeeHint')}
    >
      <div className='flex flex-wrap items-end gap-3'>
        <DateRange from={from} to={to} setFrom={setFrom} setTo={setTo} />
        <Select value={wc} onValueChange={setWc}>
          <SelectTrigger className='max-w-72 min-w-44' data-testid='oee-wc'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('mes.eqp.allWorkcenters')}</SelectItem>
            {wcs.map((w) => (
              <SelectItem key={w} value={w}>
                {w}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          className='w-56'
          value={kw}
          onChange={(e) => setKw(e.target.value)}
          placeholder={t('mes.eqp.search')}
        />
      </div>
      <Card className='gap-3'>
        <CardHeader>
          <CardTitle className='text-base'>
            {t('mes.report.oeeTrend')}
          </CardTitle>
        </CardHeader>
        <CardContent className='h-64'>
          <ResponsiveContainer width='100%' height='100%'>
            <LineChart data={chart}>
              <CartesianGrid strokeDasharray='3 3' className='stroke-muted' />
              <XAxis dataKey='day' fontSize={12} />
              <YAxis unit='%' domain={[0, 100]} fontSize={12} />
              <Tooltip
                formatter={(v) =>
                  typeof v === 'number' ? `${v.toFixed(1)}%` : '—'
                }
              />
              <Legend />
              <Line
                dataKey={t('mes.report.availability')}
                stroke='#3b82f6'
                connectNulls
              />
              <Line
                dataKey={t('mes.report.quality')}
                stroke='#16a34a'
                connectNulls
              />
              <Line
                dataKey={t('mes.report.oee')}
                stroke='#f59e0b'
                strokeWidth={2}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
      <DataCard
        title={t('menu.mes-oee-report')}
        rows={rows}
        max={500}
        exportName={`oee_${from}_${to}`}
        cols={[
          {
            head: t('mes.eqp.workcenter'),
            get: (r) => r.workcenter ?? '—',
          },
          {
            head: t('mes.report.equipment'),
            get: (r) => <span className='font-mono'>{r.equipment}</span>,
            text: (r) => r.equipment,
          },
          {
            head: t('mes.report.loading'),
            get: (r) => r.loading_h,
            right: true,
          },
          { head: t('mes.report.prd'), get: (r) => r.prd_h, right: true },
          {
            head: t('mes.report.availability'),
            get: (r) => pct(r.availability),
            right: true,
          },
          {
            head: t('mes.report.performance'),
            right: true,
            text: (r) => pct(r.performance),
            get: (r) =>
              r.uph_missing ? (
                <Badge variant='outline'>{t('mes.report.uphMissing')}</Badge>
              ) : (
                pct(r.performance)
              ),
          },
          {
            head: t('mes.report.quality'),
            get: (r) => pct(r.quality),
            right: true,
          },
          {
            head: t('mes.report.oee'),
            right: true,
            text: (r) => pct(r.oee),
            get: (r) => <span className='font-semibold'>{pct(r.oee)}</span>,
          },
          { head: t('mes.report.good'), get: (r) => r.good, right: true },
          { head: t('mes.report.scrap'), get: (r) => r.scrap, right: true },
        ]}
      />
    </Page>
  )
}
