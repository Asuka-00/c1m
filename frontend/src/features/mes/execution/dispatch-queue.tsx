/** 派工队列与扫码框：批次作业页未选批次时显示。 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { PauseCircle, ScanLine } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import { execApi, type QueueRow } from '@/lib/api/mes/execution'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  DataTable,
  clientList,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { enumLabel } from '@/features/mes/common/labels'

/** 去重选项。 */
const opts = (vs: (string | null)[]) =>
  [...new Set(vs.filter(Boolean) as string[])]
    .sort()
    .map((v) => ({ value: v, label: v }))

/**
 * 扫码 / 输入批次号，回车按批次号精确定位。
 *
 * @param onLot - 定位到批次后的回调（批次 id）
 */
export function LotScan({ onLot }: { onLot: (id: string) => void }) {
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const go = async () => {
    const c = code.trim()
    if (!c) return
    setBusy(true)
    try {
      const r = await mesApi.list('lot', { q: c, page_size: 20 })
      const hit = r.data.find(
        (x) => String(x.code).toLowerCase() === c.toLowerCase()
      )
      if (hit) {
        setCode('')
        onLot(hit.id)
      } else toast.error(t('mes.queue.notFound', { code: c }))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className='relative w-full max-w-xs'>
      <ScanLine className='absolute start-2.5 top-2.5 size-4 text-muted-foreground' />
      <Input
        autoFocus
        className='ps-8 font-mono'
        value={code}
        disabled={busy}
        placeholder={t('mes.queue.scan')}
        onChange={(e) => setCode(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && go()}
        data-testid='lot-scan'
      />
    </div>
  )
}

/**
 * 派工队列：在制批次按“非 Hold → 优先级 → Q-Time 剩余 → 滞留时长”排序，
 * 支持关键字 / 状态 / 产品 / 工序 / Hold 筛选，点击行进入批次作业。
 *
 * @param onLot - 选择批次的回调（批次 id）
 */
export function DispatchQueue({ onLot }: { onLot: (id: string) => void }) {
  const tk = useTenantKey()
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'queue'],
    queryFn: execApi.queue,
    refetchInterval: 60_000,
  })
  const all = useMemo(() => q.data ?? [], [q.data])
  const filters: FilterDef[] = [
    { type: 'text', name: 'q', placeholder: t('mes.queue.search') },
    {
      type: 'select',
      name: 'lot_status',
      label: t('mes.queue.allStatuses'),
      options: [...new Set(all.map((r) => r.lot_status))].map((v) => ({
        value: v,
        label: enumLabel('lot_status', v),
      })),
    },
    {
      type: 'select',
      name: 'product',
      label: t('mes.queue.allProducts'),
      options: opts(all.map((r) => r.product)),
    },
    {
      type: 'select',
      name: 'operation',
      label: t('mes.queue.allOperations'),
      options: opts(all.map((r) => r.operation)),
    },
    {
      type: 'select',
      name: 'on_hold',
      label: t('mes.queue.allHold'),
      options: [
        { value: 'false', label: t('mes.queue.notHeld') },
        { value: 'true', label: t('mes.queue.held') },
      ],
    },
  ]
  const lp = useListParams(filters)
  const view = clientList(all, lp, { text: (r) => `${r.code} ${r.product}` })
  const num = 'text-right tabular-nums'
  return (
    <DataTable<QueueRow>
      rows={view.rows}
      total={view.total}
      params={lp}
      filters={filters}
      loading={q.isLoading}
      rowKey={(r) => r.id}
      empty={t('mes.queue.empty')}
      columns={[
        {
          header: t('mes.queue.lot'),
          sortKey: 'code',
          cell: (r) => (
            <button
              type='button'
              className='inline-flex items-center gap-1 font-mono text-blue-600 hover:underline dark:text-blue-400'
              onClick={() => onLot(r.id)}
            >
              {r.on_hold && <PauseCircle className='size-3.5 text-amber-600' />}
              {r.code}
            </button>
          ),
        },
        {
          header: t('mes.queue.priority'),
          sortKey: 'priority_level',
          cell: (r) =>
            r.priority ? (
              <Badge
                variant='outline'
                style={{ borderColor: r.priority_color ?? undefined }}
              >
                {r.priority}
              </Badge>
            ) : (
              '—'
            ),
        },
        {
          header: t('mes.queue.product'),
          sortKey: 'product',
          cell: (r) => r.product ?? '—',
        },
        {
          header: t('mes.queue.step'),
          sortKey: 'step_seq',
          cell: (r) =>
            r.step_seq == null ? (
              '—'
            ) : (
              <span title={r.operation_name ?? undefined}>
                {r.step_seq} · {r.operation}
              </span>
            ),
        },
        {
          header: t('mes.queue.status'),
          cell: (r) => (
            <span className='inline-flex gap-1'>
              <Badge variant='secondary'>
                {enumLabel('lot_status', r.lot_status)}
              </Badge>
              {r.on_hold && (
                <Badge className='bg-amber-500 text-white'>Hold</Badge>
              )}
            </span>
          ),
        },
        {
          header: t('mes.queue.qty'),
          className: num,
          cell: (r) => r.qty,
        },
        {
          header: t('mes.queue.qtime'),
          sortKey: 'qtime_remaining',
          className: num,
          cell: (r) =>
            r.qtime_remaining == null ? (
              '—'
            ) : (
              <span
                className={
                  r.qtime_remaining < 0 ? 'font-medium text-destructive' : ''
                }
              >
                {r.qtime_remaining}
              </span>
            ),
        },
        {
          header: t('mes.queue.hours'),
          sortKey: 'hours',
          className: num,
          cell: (r) => r.hours ?? '—',
        },
        {
          header: '',
          cell: (r) => (
            <span className='flex justify-end'>
              <Button size='sm' variant='outline' onClick={() => onLot(r.id)}>
                {t('mes.queue.open')}
              </Button>
            </span>
          ),
        },
      ]}
    />
  )
}
