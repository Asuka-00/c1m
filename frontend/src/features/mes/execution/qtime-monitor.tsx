/** Q-Time 监控页面：等待中批次的计时、剩余时间与超时状态，可立即执行超时扫描。 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { RefreshCw, ScanSearch } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi, type QtimeRow } from '@/lib/api/mes/execution'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  DataTable,
  Page,
  clientList,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { RefLink } from '@/features/mes/common/ref-link'
import { mesErrorMessage } from '@/features/mes/common/required'

/** 自动刷新间隔（毫秒）。 */
const REFRESH_MS = 60_000

/** 行的计时状态：已 Hold / 已超时 / 即将超时 / 计时中。 */
function stateOf(r: QtimeRow): 'held' | 'exceeded' | 'warn' | 'ok' {
  if (r.on_hold) return 'held'
  if (r.exceeded) return 'exceeded'
  if (r.warn) return 'warn'
  return 'ok'
}

/** 取行中某字段的去重选项。 */
function distinct(rows: QtimeRow[], k: 'product' | 'route') {
  return [...new Set(rows.map((r) => r[k]).filter(Boolean) as string[])]
    .sort()
    .map((v) => ({ value: v, label: v }))
}

/** Q-Time 监控。 */
export default function QtimeMonitor() {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const [auto, setAuto] = useState(true)
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'qtime-monitor'],
    queryFn: execApi.qtimeMonitor,
    refetchInterval: auto ? REFRESH_MS : false,
  })
  const all = useMemo(() => q.data ?? [], [q.data])
  const filters: FilterDef[] = [
    { type: 'text', name: 'q', placeholder: t('mes.qtime.search') },
    {
      type: 'select',
      name: 'state',
      label: t('mes.qtime.allStates'),
      options: (['exceeded', 'warn', 'ok', 'held'] as const).map((v) => ({
        value: v,
        label: t(`mes.qtime.${v}`),
      })),
    },
    {
      type: 'select',
      name: 'product',
      label: t('mes.qtime.allProducts'),
      options: distinct(all, 'product'),
    },
    {
      type: 'select',
      name: 'route',
      label: t('mes.qtime.allRoutes'),
      options: distinct(all, 'route'),
    },
  ]
  const lp = useListParams(filters)
  const view = clientList(all, lp, {
    text: (r) => `${r.lot} ${r.rule}`,
    match: { state: (r, v) => stateOf(r) === v },
  })
  const sweep = useMutation({
    mutationFn: execApi.qtimeSweep,
    onSuccess: (r) => {
      toast.success(
        t('mes.qtime.swept', { checked: r.checked, acted: r.actions.length })
      )
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  const num = 'text-right tabular-nums'
  return (
    <Page
      title={t('menu.mes-qtime-monitor')}
      description={t('mes.qtime.hint')}
      actions={
        <>
          <div className='flex items-center gap-2'>
            <Switch
              id='qtime-auto'
              checked={auto}
              onCheckedChange={setAuto}
              data-testid='qtime-auto'
            />
            <Label htmlFor='qtime-auto' className='text-sm'>
              {t('mes.qtime.autoRefresh')}
            </Label>
          </div>
          <Button variant='outline' onClick={() => q.refetch()}>
            <RefreshCw className='size-4' />
            {t('mes.qtime.refresh')}
          </Button>
          <Button
            onClick={() => sweep.mutate()}
            disabled={sweep.isPending}
            data-testid='qtime-sweep'
          >
            <ScanSearch className='size-4' />
            {t('mes.qtime.sweep')}
          </Button>
        </>
      }
    >
      <DataTable
        rows={view.rows}
        total={view.total}
        params={lp}
        filters={filters}
        loading={q.isLoading}
        rowKey={(r) => `${r.lot_id}-${r.rule}`}
        columns={[
          {
            header: t('mes.qtime.lot'),
            sortKey: 'lot',
            cell: (r) => <RefLink target='lot' id={r.lot_id} label={r.lot} />,
          },
          {
            header: t('mes.qtime.product'),
            sortKey: 'product',
            cell: (r) => r.product ?? '—',
          },
          {
            header: t('mes.qtime.route'),
            sortKey: 'route',
            cell: (r) => r.route ?? '—',
          },
          {
            header: t('mes.qtime.step'),
            sortKey: 'step_seq',
            cell: (r) => r.step_seq,
          },
          {
            header: t('mes.qtime.rule'),
            cell: (r) => <span className='font-mono'>{r.rule}</span>,
          },
          {
            header: t('mes.qtime.since'),
            sortKey: 'since',
            cell: (r) => fmtDateTime(r.since),
          },
          {
            header: t('mes.qtime.elapsed'),
            sortKey: 'minutes',
            className: num,
            cell: (r) => r.minutes,
          },
          {
            header: t('mes.qtime.warnAt'),
            className: num,
            cell: (r) => r.warn_minutes ?? '—',
          },
          {
            header: t('mes.qtime.max'),
            className: num,
            cell: (r) => r.max_minutes ?? '—',
          },
          {
            header: t('mes.qtime.remaining'),
            sortKey: 'remaining',
            className: num,
            cell: (r) => (
              <span
                className={
                  r.exceeded
                    ? 'font-medium text-destructive'
                    : r.warn
                      ? 'font-medium text-amber-600'
                      : ''
                }
              >
                {r.remaining ?? '—'}
              </span>
            ),
          },
          {
            header: t('mes.qtime.action'),
            cell: (r) => t(`mes.qtime.act.${r.action}`),
          },
          {
            header: t('mes.qtime.state'),
            cell: (r) => <QtimeBadge state={stateOf(r)} />,
          },
        ]}
      />
    </Page>
  )
}

/** Q-Time 状态徽标。 */
function QtimeBadge({ state }: { state: ReturnType<typeof stateOf> }) {
  if (state === 'held')
    return <Badge variant='secondary'>{t('mes.qtime.held')}</Badge>
  if (state === 'exceeded')
    return <Badge variant='destructive'>{t('mes.qtime.exceeded')}</Badge>
  if (state === 'warn')
    return (
      <Badge className='bg-amber-500 text-white'>{t('mes.qtime.warn')}</Badge>
    )
  return <Badge variant='outline'>{t('mes.qtime.ok')}</Badge>
}
