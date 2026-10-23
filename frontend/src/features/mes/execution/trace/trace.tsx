/** 追溯查询页面：按批次 / 晶圆 / 设备 / 物料批做正向与反向追溯。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import { Search } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi, type TraceKind, type TraceRow } from '@/lib/api/mes/execution'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Page } from '@/components/crud'
import { enumLabel } from '@/features/mes/common/labels'
import { mesErrorMessage } from '@/features/mes/common/required'
import { Pick } from '../shared/exec-parts'

const KINDS: TraceKind[] = ['lot', 'wafer', 'equipment', 'material_lot']

/** 单元格显示：时间格式化、数组（消耗 / 下游）压缩成文本。 */
function cell(col: string, v: unknown): React.ReactNode {
  if (v === null || v === undefined || v === '') return '—'
  if (col === 'at') return fmtDateTime(String(v))
  if (col === 'relation') return enumLabel('genealogy_relation', String(v))
  if (Array.isArray(v))
    return v.length
      ? v
          .map((x: Record<string, unknown>) =>
            col === 'consumed'
              ? `${String(x.material_lot)}×${String(x.qty)}`
              : String(x.code)
          )
          .join(', ')
      : '—'
  return String(v)
}

/** 追溯结果表（lot / code 列可跳转到批次履历）。 */
function TraceTable({
  title,
  rows,
  cols,
}: {
  title: string
  rows: TraceRow[]
  cols: string[]
}) {
  return (
    <Card className='gap-3'>
      <CardHeader>
        <CardTitle className='text-base'>
          {title} ({rows.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              {cols.map((c) => (
                <TableHead key={c}>{t(`mes.traceq.c.${c}`)}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={cols.length}
                  className='text-center text-muted-foreground'
                >
                  {t('common.noResults')}
                </TableCell>
              </TableRow>
            )}
            {rows.slice(0, 200).map((r, i) => (
              <TableRow key={i}>
                {cols.map((c) => (
                  <TableCell
                    key={c}
                    className={c === 'code' || c === 'lot' ? 'font-mono' : ''}
                  >
                    {c === 'code' && r.id ? (
                      <Link
                        to='/$'
                        params={{ _splat: 'mes/lot-history' }}
                        search={
                          { tab: 'mes-lot-trace', lot: String(r.id) } as never
                        }
                        className='underline-offset-2 hover:underline'
                      >
                        {String(r.code)}
                      </Link>
                    ) : (
                      cell(c, r[c])
                    )}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

/** 追溯查询。 */
export default function TracePage() {
  const tk = useTenantKey()
  const [kind, setKind] = useState<TraceKind>('lot')
  const [code, setCode] = useState('')
  const [query, setQuery] = useState<{ kind: TraceKind; code: string } | null>(
    null
  )
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'trace', query],
    queryFn: () => execApi.trace(query!.kind, query!.code),
    enabled: !!query,
    retry: false,
  })
  const d = q.data
  return (
    <Page title={t('menu.mes-trace')} description={t('mes.traceq.hint')}>
      <form
        className='mb-4 flex flex-wrap items-end gap-3'
        onSubmit={(e) => {
          e.preventDefault()
          if (code.trim()) setQuery({ kind, code: code.trim() })
        }}
      >
        <div className='w-40'>
          <Pick
            id='trace-kind'
            label={t('mes.traceq.kind')}
            none={false}
            value={kind}
            onChange={(v) => setKind(v as TraceKind)}
            options={KINDS.map((k) => ({
              id: k,
              label: t(`mes.traceq.k.${k}`),
            }))}
          />
        </div>
        <div className='grid w-64 gap-1'>
          <label htmlFor='trace-code' className='text-sm font-medium'>
            {t('mes.traceq.code')}
          </label>
          <Input
            id='trace-code'
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </div>
        <Button type='submit' data-testid='trace-search'>
          <Search className='size-4' />
          {t('mes.traceq.search')}
        </Button>
      </form>
      {q.error && (
        <p className='text-sm text-destructive'>
          {mesErrorMessage(q.error, undefined)}
        </p>
      )}
      {d?.backward && (
        <div className='grid gap-4'>
          <h3 className='font-semibold'>
            {t('mes.traceq.backward')} · {d.target.code}
          </h3>
          <TraceTable
            title={t('mes.traceq.srcLots')}
            rows={d.backward.lots}
            cols={['code', 'relation', 'qty', 'via', 'level', 'at']}
          />
          <TraceTable
            title={t('mes.traceq.steps')}
            rows={d.backward.steps}
            cols={[
              'lot',
              'step_seq',
              'operation',
              'equipment',
              'recipe',
              'user',
              'at',
            ]}
          />
          <TraceTable
            title={t('mes.traceq.materials')}
            rows={d.backward.materials}
            cols={['lot', 'step_seq', 'material_lot', 'qty', 'at']}
          />
          <h3 className='font-semibold'>{t('mes.traceq.forward')}</h3>
          <TraceTable
            title={t('mes.traceq.outLots')}
            rows={d.forward?.lots ?? []}
            cols={['code', 'relation', 'qty', 'via', 'level', 'at']}
          />
          <TraceTable
            title={t('mes.traceq.shipments')}
            rows={d.forward?.shipments ?? []}
            cols={['lot', 'shipment', 'customer', 'waybill', 'qty', 'at']}
          />
        </div>
      )}
      {d?.lots && (
        <TraceTable
          title={`${t('mes.traceq.lots')} · ${d.target.code}`}
          rows={d.lots.map((r) => ({ ...r, downstream: r.forward }))}
          cols={
            d.kind === 'equipment'
              ? ['code', 'product', 'step_seq', 'operation', 'qty', 'at']
              : ['code', 'product', 'step_seq', 'consumed', 'downstream', 'at']
          }
        />
      )}
    </Page>
  )
}
