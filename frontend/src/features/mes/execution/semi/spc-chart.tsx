/** SPC 控制图页面：DC 计划项的 X-bar 图（控制限 / 规格限 + 判异点）与子组明细。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { useTenantKey } from '@/lib/api/hooks'
import { semiApi, type SpcChart } from '@/lib/api/mes/semi'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Page } from '@/components/crud'
import { RefLink } from '@/features/mes/common/ref-link'
import { RefSelect } from '@/features/mes/common/ref-select'
import { yRange } from './semi-utils'

const W = 720
const H = 260
const PAD = 36

const LINES = [
  ['usl', 'stroke-destructive', '6 3'],
  ['ucl', 'stroke-amber-500', '3 3'],
  ['cl', 'stroke-emerald-600', ''],
  ['lcl', 'stroke-amber-500', '3 3'],
  ['lsl', 'stroke-destructive', '6 3'],
] as const

function Chart({ c }: { c: SpcChart }) {
  const [lo, hi] = yRange(c)
  const y = (v: number) => H - PAD - ((v - lo) / (hi - lo)) * (H - 2 * PAD)
  const n = c.points.length
  const x = (i: number) =>
    n <= 1 ? W / 2 : PAD + (i * (W - 2 * PAD)) / (n - 1)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className='w-full' role='img'>
      {LINES.map(([k, cls, dash]) => {
        const v = c.limits[k]
        if (v == null) return null
        return (
          <g key={k}>
            <line
              x1={PAD}
              x2={W - PAD}
              y1={y(v)}
              y2={y(v)}
              className={cls}
              strokeDasharray={dash}
            />
            <text
              x={W - PAD + 4}
              y={y(v) + 4}
              className='fill-muted-foreground text-[10px]'
            >
              {k.toUpperCase()}
            </text>
          </g>
        )
      })}
      <polyline
        fill='none'
        className='stroke-sky-600'
        points={c.points.map((p, i) => `${x(i)},${y(p.mean)}`).join(' ')}
      />
      {c.points.map((p, i) => (
        <circle
          key={i}
          cx={x(i)}
          cy={y(p.mean)}
          r={p.rules.length ? 4.5 : 3}
          className={p.rules.length ? 'fill-destructive' : 'fill-sky-600'}
        >
          <title>{`${p.lot} · ${p.mean}`}</title>
        </circle>
      ))}
    </svg>
  )
}

/** SPC 控制图。 */
export default function SpcChartPage() {
  const tk = useTenantKey()
  const [item, setItem] = useState<{ id: string; label: string } | null>(null)
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'spc', item?.id],
    queryFn: () => semiApi.spc(item!.id),
    enabled: !!item,
  })
  const c = q.data
  return (
    <Page title={t('menu.mes-spc-chart')} description={t('mes.semi.spcHint')}>
      <div className='max-w-sm'>
        <Label htmlFor='spc-item'>{t('mes.entity.dc_plan_item')}</Label>
        <RefSelect
          id='spc-item'
          target='dc_plan_item'
          labelField='measurement_item_label'
          value={item?.id ?? null}
          label={item?.label ?? null}
          onChange={(id, label) =>
            setItem(id ? { id, label: label ?? '' } : null)
          }
        />
      </div>
      {c && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className='flex flex-wrap items-center gap-2'>
                {c.item ? `${c.item.code} · ${c.item.name}` : '—'}
                {c.plan && (
                  <span className='text-sm font-normal text-muted-foreground'>
                    {c.plan.code}
                  </span>
                )}
                <span className='ms-auto text-sm font-normal text-muted-foreground'>
                  {c.rules.length
                    ? t('mes.semi.rules', { rules: c.rules.join(', ') })
                    : t('mes.semi.noRules')}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {c.points.length ? (
                <Chart c={c} />
              ) : (
                <p className='text-sm text-muted-foreground'>
                  {t('mes.semi.spcEmpty')}
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardContent className='pt-6'>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('mes.field.lot.code')}</TableHead>
                    <TableHead>{t('mes.exec.step')}</TableHead>
                    <TableHead>{t('mes.semi.mean')}</TableHead>
                    <TableHead>n</TableHead>
                    <TableHead>{t('mes.field.dc_result.ooc_rules')}</TableHead>
                    <TableHead>{t('mes.at')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...c.points].reverse().map((p, i) => (
                    <TableRow key={i}>
                      <TableCell>
                        <RefLink target='lot' id={p.lot_id} label={p.lot} />
                      </TableCell>
                      <TableCell>{p.step_seq ?? '—'}</TableCell>
                      <TableCell className='tabular-nums'>{p.mean}</TableCell>
                      <TableCell className='tabular-nums'>{p.n}</TableCell>
                      <TableCell>
                        {p.rules.length ? (
                          <Badge variant='destructive'>
                            {p.rules.join(', ')}
                          </Badge>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell>{fmtDateTime(p.at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </Page>
  )
}
