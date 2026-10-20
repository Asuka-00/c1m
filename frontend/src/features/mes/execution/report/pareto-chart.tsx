/** 报废原因帕累托图：数量柱 + 累计占比折线。 */
import { t } from '@/i18n'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ParetoRow } from '@/lib/api/mes/execution'
import { pct } from './report-utils'

/**
 * 帕累托图；无数据时显示空状态。
 *
 * @param rows - 按数量降序的报废原因
 */
export function ParetoChart({ rows }: { rows: ParetoRow[] }) {
  if (!rows.length)
    return (
      <p className='py-10 text-center text-sm text-muted-foreground'>
        {t('mes.yield.noScrap')}
      </p>
    )
  const data = rows.map((r) => ({
    reason: r.reason,
    [t('mes.yield.qty')]: r.qty,
    [t('mes.yield.cum')]: r.cum_pct * 100,
  }))
  return (
    <div className='h-64' data-testid='pareto'>
      <ResponsiveContainer width='100%' height='100%'>
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray='3 3' className='stroke-muted' />
          <XAxis dataKey='reason' fontSize={12} />
          <YAxis yAxisId='q' fontSize={12} allowDecimals={false} />
          <YAxis
            yAxisId='p'
            orientation='right'
            unit='%'
            domain={[0, 100]}
            fontSize={12}
          />
          <Tooltip
            formatter={(v, n) =>
              n === t('mes.yield.cum') && typeof v === 'number'
                ? pct(v / 100)
                : String(v)
            }
          />
          <Bar yAxisId='q' dataKey={t('mes.yield.qty')} fill='#ef4444' />
          <Line yAxisId='p' dataKey={t('mes.yield.cum')} stroke='#3b82f6' dot />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
