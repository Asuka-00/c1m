/** 追溯查询页面：按批次 / 晶圆 / 设备 / 物料批 / 客户批号做正向与反向追溯。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import { Search } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import {
  type CustomerLotTrace,
  execApi,
  type TraceKind,
  type TraceResult,
  type TraceRow,
} from '@/lib/api/mes/execution'
import {
  isBlankTraceCode,
  markingApi,
  type TraceCodeResult,
} from '@/lib/api/mes/marking'
import { Badge } from '@/components/ui/badge'
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
import { CustomerBadges, OwnershipLabel } from '@/features/mes/common/customer'
import { enumLabel } from '@/features/mes/common/labels'
import { mesErrorMessage } from '@/features/mes/common/required'
import {
  markingErrorMessage,
  traceErrorTexts,
  useTraceConfig,
} from '@/features/mes/marking/marking-rules'
import { Pick } from './exec-parts'
import { genealogyRows } from './trace-rows'

/** 单位转换位置映射的列（F4：从子批查回母晶圆和 die 坐标）。 */
const ORIGIN_COLS = [
  'child_lot',
  'child_seq',
  'child_unit',
  'parent_lot',
  'parent_wafer',
  'die_row',
  'die_col',
  'qty',
]

const KINDS: TraceKind[] = [
  'lot',
  'wafer',
  'equipment',
  'material_lot',
  'customer_lot',
  'trace_code',
]

/** 批次表的列（含客户批号与归属，F6）。 */
const LOT_COLS = [
  'code',
  'customer_lot_no',
  'ownership',
  'relation',
  'qty',
  'via',
  'level',
  'at',
  'transform_id',
]

/** 单元格显示：时间格式化、数组（消耗 / 下游）压缩成文本。 */
function cell(col: string, v: unknown, row: TraceRow): React.ReactNode {
  if (col === 'ownership')
    return row.code || row.lot_no ? <OwnershipLabel info={row as never} /> : '—'
  if (v === null || v === undefined || v === '') return '—'
  if (col === 'at' || col === 'marked_at') return fmtDateTime(String(v))
  if (col === 'latest_inspection_status')
    return t(`mes.marking.insp.${String(v)}`)
  if (col === 'relation') {
    const rel = enumLabel('genealogy_relation', String(v))
    return row.undone === true ? <UndoneRelation rel={rel} row={row} /> : rel
  }
  // D54：转换谱系带转换记录 id（撤销后记录仍保留），显示前 8 位，悬停看全文
  if (col === 'transform_id')
    return (
      <span className='font-mono text-xs' title={String(v)}>
        {String(v).slice(0, 8)}
      </span>
    )
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

/**
 * D60：已撤销的转换节点只做展示（标「已撤销」及撤销时间 / 人 / 原因，缺失的不显示），
 * 不参与谱系关系。
 */
function UndoneRelation({ rel, row }: { rel: string; row: TraceRow }) {
  const s = (x: unknown) => (x == null || x === '' ? null : String(x))
  const at = s(row.undone_at)
  const info = [
    at && fmtDateTime(at),
    s(row.undone_by),
    s(row.undo_reason),
  ].filter(Boolean)
  return (
    <span className='inline-flex flex-wrap items-center gap-1'>
      <span className='text-muted-foreground line-through'>{rel}</span>
      <Badge variant='secondary' data-testid='trace-undone'>
        {t('mes.tundo.undone')}
      </Badge>
      {info.length > 0 && (
        <span
          className='text-xs text-muted-foreground'
          data-testid='trace-undone-info'
        >
          {info.join(' · ')}
        </span>
      )}
    </span>
  )
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
          {title} ({genealogyRows(rows).length})
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
                    className={
                      [
                        'code',
                        'lot',
                        'child_lot',
                        'parent_lot',
                        'parent_wafer',
                        'child_unit',
                      ].includes(c)
                        ? 'font-mono'
                        : ''
                    }
                  >
                    {c === 'code' && r.id && r.undone !== true ? (
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
                      cell(c, r[c], r)
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
  const [includeVoided, setIncludeVoided] = useState(false)
  const isCode = query?.kind === 'trace_code'
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'trace', query],
    queryFn: () => execApi.trace(query!.kind, query!.code),
    enabled: !!query && !isCode,
    retry: false,
  })
  // D79-6：kind=trace_code 单独形状；默认不含已作废，开关打开传 include_voided=true
  const tq = useQuery({
    queryKey: ['mes', 'exec', tk, 'trace-code', query?.code, includeVoided],
    queryFn: () => markingApi.trace(query!.code, includeVoided),
    enabled: !!query && isCode,
    retry: false,
  })
  const [codeErr, setCodeErr] = useState<string[]>([])
  const { rule, patternInvalid } = useTraceConfig()
  const d = q.data
  return (
    <Page title={t('menu.mes-trace')} description={t('mes.traceq.hint')}>
      <form
        className='mb-4 flex flex-wrap items-end gap-3'
        onSubmit={(e) => {
          e.preventDefault()
          // trace_code 原值提交（D78 补充四）；其他类型沿用去空格
          const c = kind === 'trace_code' ? code : code.trim()
          // D78：追溯码 ≤32、[A-Z0-9-]，前端先校验（同后端 422 value_error ctx.reason）
          const bad = kind === 'trace_code' ? traceErrorTexts(c, rule) : []
          setCodeErr(bad)
          if (c && !isBlankTraceCode(c) && !bad.length)
            setQuery({ kind, code: c })
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
        {kind === 'trace_code' && (
          <label className='flex items-center gap-2 pb-2 text-sm'>
            <input
              type='checkbox'
              checked={includeVoided}
              onChange={(e) => setIncludeVoided(e.target.checked)}
              data-testid='trace-include-voided'
            />
            {t('mes.traceq.includeVoided')}
          </label>
        )}
        <Button type='submit' data-testid='trace-search'>
          <Search className='size-4' />
          {t('mes.traceq.search')}
        </Button>
      </form>
      {kind === 'trace_code' && patternInvalid && (
        <p
          className='text-xs text-muted-foreground'
          data-testid='trace-pattern-invalid'
        >
          {t('mes.marking.patternInvalidHint')}
        </p>
      )}
      {codeErr.length > 0 && (
        <div className='text-sm text-destructive' data-testid='trace-code-err'>
          {codeErr.map((m) => (
            <p key={m}>{m}</p>
          ))}
        </div>
      )}
      {isCode && tq.data && <TraceCodeBlock r={tq.data} />}
      {isCode && tq.error && (
        <p
          className='text-sm text-destructive'
          data-testid='trace-code-api-err'
        >
          {markingErrorMessage(tq.error)}
        </p>
      )}
      {!isCode && q.error && (
        <p className='text-sm text-destructive'>
          {mesErrorMessage(q.error, undefined)}
        </p>
      )}
      {!isCode && d?.backward && (
        <LotTraceBlock
          title={d.target.code ?? ''}
          info={d.target}
          backward={d.backward}
          forward={d.forward}
        />
      )}
      {d?.kind === 'customer_lot' && <CustomerLotResult d={d} />}
      {d?.lots && d.kind !== 'customer_lot' && (
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

/** 一个批次的反向 / 正向追溯（批次 / 晶圆查询，以及客户批号查到的每个批次）。 */
function LotTraceBlock({
  title,
  info,
  backward,
  forward,
}: {
  title: string
  info: TraceResult['target']
  backward: NonNullable<TraceResult['backward']>
  forward?: TraceResult['forward']
}) {
  return (
    <div className='grid gap-4'>
      <h3 className='flex flex-wrap items-center gap-2 font-semibold'>
        {t('mes.traceq.backward')} · {title}
        <CustomerBadges info={info} />
      </h3>
      <TraceTable
        title={t('mes.traceq.srcLots')}
        rows={backward.lots}
        cols={LOT_COLS}
      />
      <TraceTable
        title={t('mes.traceq.steps')}
        rows={backward.steps}
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
        rows={backward.materials}
        cols={['lot', 'step_seq', 'material_lot', 'qty', 'at']}
      />
      {!!backward.origins?.length && (
        <TraceTable
          title={t('mes.traceq.origins')}
          rows={backward.origins}
          cols={ORIGIN_COLS}
        />
      )}
      <h3 className='font-semibold'>{t('mes.traceq.forward')}</h3>
      <TraceTable
        title={t('mes.traceq.outLots')}
        rows={forward?.lots ?? []}
        cols={LOT_COLS}
      />
      {!!forward?.dies?.length && (
        <TraceTable
          title={t('mes.traceq.dies')}
          rows={forward.dies}
          cols={ORIGIN_COLS}
        />
      )}
      {!!forward?.origins?.length && (
        <TraceTable
          title={t('mes.traceq.outOrigins')}
          rows={forward.origins}
          cols={ORIGIN_COLS}
        />
      )}
    </div>
  )
}

/** 按客户批号查询（F6-03）：先列出匹配的批次，再逐批显示追溯。 */
function CustomerLotResult({ d }: { d: TraceResult }) {
  const hits = (d.lots ?? []) as unknown as CustomerLotTrace[]
  return (
    <div className='grid gap-6' data-testid='customer-lot-result'>
      <TraceTable
        title={`${t('mes.traceq.lots')} · ${d.target.customer_lot_no ?? ''}`}
        rows={hits.map((h) => ({
          ...h,
          id: h.lot_id ?? h.lot_no,
          code: h.lot_no,
          lot_status: enumLabel('lot_status', h.lot_status),
        }))}
        cols={['code', 'customer_lot_no', 'ownership', 'lot_status']}
      />
      {hits.map(
        (h) =>
          (h.backward || h.forward) && (
            <LotTraceBlock
              key={h.lot_id ?? h.lot_no}
              title={h.lot_no}
              info={h}
              backward={h.backward ?? { lots: [], steps: [], materials: [] }}
              forward={h.forward}
            />
          )
      )}
    </div>
  )
}

/** kind=trace_code 结果：主记录 + 各次打印的检验结果（D79-6）。 */
function TraceCodeBlock({ r }: { r: TraceCodeResult }) {
  return (
    <div className='grid gap-3' data-testid='trace-code-result'>
      <h3 className='flex flex-wrap items-center gap-2 font-semibold'>
        <span className='font-mono'>{r.trace_code}</span>
        <Link
          to='/$'
          params={{ _splat: 'mes/lot-history' }}
          search={{ tab: 'mes-lot-trace', lot: r.lot_id } as never}
          className='text-sm font-normal underline-offset-2 hover:underline'
        >
          {t('mes.traceq.c.lot')}
        </Link>
        {r.voided && (
          <Badge variant='outline' data-testid='trace-code-voided'>
            {t('mes.marking.voided')}
          </Badge>
        )}
      </h3>
      <TraceTable
        title={t('mes.traceq.marking')}
        rows={r.prints.map((p) => ({
          seq: p.seq,
          marked_at: p.marked_at,
          latest_inspection_status: p.latest_inspection_result,
        }))}
        cols={['seq', 'marked_at', 'latest_inspection_status']}
      />
    </div>
  )
}
