/** 设备状态看板：E10 当前状态、PM 到期、停机标记；支持手动改状态与登记 PM 完成。 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import { eqpApi, type BoardRow } from '@/lib/api/mes/equipment'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  DataTable,
  Page,
  boolOptions,
  clientList,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { optLabel } from '@/features/mes/common/labels'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesMeta } from '@/features/mes/common/use-mes-meta'
import { Pick } from '@/features/mes/execution/exec-parts'

/** 去重选项。 */
const opts = (vs: (string | null | undefined)[]) =>
  [...new Set(vs.filter(Boolean) as string[])]
    .sort()
    .map((v) => ({ value: v, label: v }))

/** 设备状态看板页面：按工作中心排序，可按工作中心 / E10 状态 / PM / 停机筛选。 */
export default function EqpBoard() {
  const tk = useTenantKey()
  const { data: meta } = useMesMeta()
  const can = (p: string) => (meta?.perms ?? []).includes(p)
  const [dlg, setDlg] = useState<{ kind: 'e10' | 'pm'; row: BoardRow } | null>(
    null
  )
  const q = useQuery({
    queryKey: ['mes', 'eqp', tk, 'board'],
    queryFn: eqpApi.board,
    refetchInterval: 60_000,
  })
  const all = useMemo(() => q.data ?? [], [q.data])
  const filters: FilterDef[] = [
    { type: 'text', name: 'q', placeholder: t('mes.eqp.search') },
    {
      type: 'select',
      name: 'workcenter',
      label: t('mes.eqp.allWorkcenters'),
      options: opts(all.map((r) => r.workcenter)),
    },
    {
      type: 'select',
      name: 'category',
      label: t('mes.eqp.allStates'),
      options: opts(all.map((r) => r.state?.category)),
    },
    {
      type: 'select',
      name: 'pm',
      label: t('mes.eqp.allPm'),
      options: [
        { value: 'due', label: t('mes.eqp.pmDue') },
        { value: 'warn', label: t('mes.eqp.pmWarn') },
      ],
    },
    {
      type: 'select',
      name: 'down',
      label: t('mes.eqp.allDown'),
      options: boolOptions(t('mes.eqp.down'), t('mes.eqp.notDown')),
    },
  ]
  const lp = useListParams(filters)
  const sorted = useMemo(
    () =>
      [...all].sort((a, b) =>
        `${a.workcenter ?? '~'} ${a.code}`.localeCompare(
          `${b.workcenter ?? '~'} ${b.code}`
        )
      ),
    [all]
  )
  const view = clientList(sorted, lp, {
    text: (r) => `${r.code} ${r.name}`,
    match: {
      category: (r, v) => r.state?.category === v,
      pm: (r, v) => (v === 'due' ? r.pm_due : r.pm_warn && !r.pm_due),
      down: (r, v) => String(!!r.down) === v,
    },
  })
  // 各 E10 状态的设备数（点击即按该状态筛选）
  const cats = Object.entries(
    all.reduce<Record<string, { n: number; color: string }>>((m, r) => {
      const k = r.state?.category ?? '—'
      m[k] = { n: (m[k]?.n ?? 0) + 1, color: r.state?.color ?? '#9ca3af' }
      return m
    }, {})
  ).sort()
  return (
    <Page
      title={t('menu.mes-eqp-board')}
      description={t('mes.eqp.hint')}
      actions={
        <Button variant='outline' onClick={() => q.refetch()}>
          <RefreshCw className='size-4' />
          {t('mes.eqp.refresh')}
        </Button>
      }
    >
      <div className='flex flex-wrap gap-2' data-testid='e10-summary'>
        {cats.map(([k, v]) => (
          <button
            key={k}
            type='button'
            onClick={() =>
              lp.setFilter('category', lp.filters.category === k ? '' : k)
            }
            className={cn(
              'inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm hover:bg-muted',
              lp.filters.category === k && 'ring-2 ring-primary'
            )}
          >
            <span
              className='size-2.5 rounded-full'
              style={{ background: v.color }}
            />
            <span className='font-mono'>{k}</span>
            <span className='font-semibold tabular-nums'>{v.n}</span>
          </button>
        ))}
      </div>
      <DataTable
        rows={view.rows}
        total={view.total}
        params={lp}
        filters={filters}
        loading={q.isLoading}
        rowKey={(r) => r.id}
        columns={[
          {
            header: t('mes.eqp.workcenter'),
            cell: (r) =>
              r.workcenter ? (
                <span title={r.workcenter_name ?? undefined}>
                  {r.workcenter}
                </span>
              ) : (
                '—'
              ),
          },
          {
            header: t('mes.eqp.code'),
            sortKey: 'code',
            cell: (r) => <span className='font-mono'>{r.code}</span>,
          },
          { header: t('mes.eqp.name'), cell: (r) => r.name },
          {
            header: t('mes.eqp.state'),
            cell: (r) => (
              <span className='inline-flex items-center gap-2'>
                <span
                  className='size-2.5 rounded-full'
                  style={{ background: r.state?.color ?? '#9ca3af' }}
                />
                {r.state ? `${r.state.code} · ${r.state.name}` : '—'}
                {r.down && (
                  <Badge variant='destructive'>{t('mes.eqp.down')}</Badge>
                )}
              </span>
            ),
          },
          {
            header: t('mes.eqp.pm'),
            cell: (r) => (
              <span className='space-x-1'>
                {r.pm.length === 0 && (
                  <span className='text-muted-foreground'>—</span>
                )}
                {r.pm.map((p) => (
                  <Badge
                    key={p.plan_id}
                    variant={
                      p.due ? 'destructive' : p.warn ? 'secondary' : 'outline'
                    }
                    title={
                      p.next_due
                        ? `${t('mes.eqp.nextDue')}: ${fmtDateTime(p.next_due)}`
                        : undefined
                    }
                  >
                    {p.plan}{' '}
                    {p.due
                      ? t('mes.eqp.pmDue')
                      : p.days_left !== null
                        ? t('mes.eqp.daysLeft', { n: p.days_left })
                        : ''}
                    {p.interval_lots
                      ? ` · ${p.lots_since}/${p.interval_lots}`
                      : ''}
                  </Badge>
                ))}
              </span>
            ),
          },
          {
            header: '',
            cell: (r) => (
              <span className='flex justify-end gap-2'>
                <Button
                  size='sm'
                  variant='outline'
                  disabled={!can('mes.equipment:e10') || r.next.length === 0}
                  onClick={() => setDlg({ kind: 'e10', row: r })}
                  data-testid={`e10-${r.code}`}
                >
                  {t('mes.eqp.changeState')}
                </Button>
                <Button
                  size='sm'
                  variant='outline'
                  disabled={!can('mes.equipment:pm') || r.pm.length === 0}
                  onClick={() => setDlg({ kind: 'pm', row: r })}
                  data-testid={`pm-${r.code}`}
                >
                  {t('mes.eqp.pmDone')}
                </Button>
              </span>
            ),
          },
        ]}
      />
      {dlg?.kind === 'e10' && (
        <E10Dialog row={dlg.row} onClose={() => setDlg(null)} />
      )}
      {dlg?.kind === 'pm' && (
        <PmDialog row={dlg.row} onClose={() => setDlg(null)} />
      )}
    </Page>
  )
}

/** 手动改 E10 状态对话框（目标状态仅列出迁移表允许的状态）。 */
function E10Dialog({ row, onClose }: { row: BoardRow; onClose: () => void }) {
  const qc = useQueryClient()
  const [to, setTo] = useState('')
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const reasons = useQuery({
    queryKey: ['mes', 'reason_code', 'e10-options'],
    queryFn: () =>
      mesApi.list('reason_code', { reason_type: 'e10', page_size: 100 }),
  })
  const target = row.next.find((n) => n.id === to)
  const m = useMutation({
    mutationFn: () =>
      eqpApi.changeE10(row.id, {
        to_state_id: to,
        reason_id: reason || undefined,
        comment: comment || undefined,
      }),
    onSuccess: () => {
      toast.success(t('mes.eqp.changed'))
      qc.invalidateQueries({ queryKey: ['mes'] })
      onClose()
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('mes.eqp.changeState')} · {row.code}
          </DialogTitle>
          <DialogDescription>
            {t('mes.eqp.current')}: {row.state?.code ?? '—'}
          </DialogDescription>
        </DialogHeader>
        <Pick
          id='e10-to'
          label={t('mes.eqp.toState')}
          required
          none={false}
          value={to}
          onChange={setTo}
          options={row.next.map((n) => ({
            id: n.id,
            label: `${n.code} · ${n.name}`,
          }))}
        />
        <Pick
          id='e10-reason'
          label={t('mes.exec.reason')}
          required={!!target?.reason_required}
          value={reason}
          onChange={setReason}
          options={(reasons.data?.data ?? []).map((r) => ({
            id: String(r.id),
            label: optLabel(r as { code: string; name?: string }),
          }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='e10-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='e10-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            disabled={
              !to || (!!target?.reason_required && !reason) || m.isPending
            }
            onClick={() => m.mutate()}
          >
            {t('mes.eqp.changeState')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 登记 PM 完成对话框。 */
function PmDialog({ row, onClose }: { row: BoardRow; onClose: () => void }) {
  const qc = useQueryClient()
  const [plan, setPlan] = useState(row.pm[0]?.plan_id ?? '')
  const [result, setResult] = useState<'ok' | 'ng'>('ok')
  const [comment, setComment] = useState('')
  const m = useMutation({
    mutationFn: () =>
      eqpApi.pmComplete(plan, {
        equipment_id: row.id,
        result,
        comment: comment || undefined,
      }),
    onSuccess: () => {
      toast.success(t('mes.eqp.pmRecorded'))
      qc.invalidateQueries({ queryKey: ['mes'] })
      onClose()
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('mes.eqp.pmDone')} · {row.code}
          </DialogTitle>
          <DialogDescription>{t('mes.eqp.pmDesc')}</DialogDescription>
        </DialogHeader>
        <Pick
          id='pm-plan'
          label={t('mes.eqp.pm')}
          required
          none={false}
          value={plan}
          onChange={setPlan}
          options={row.pm.map((p) => ({ id: p.plan_id, label: p.plan }))}
        />
        <Pick
          id='pm-result'
          label={t('mes.eqp.result')}
          required
          none={false}
          value={result}
          onChange={(v) => setResult(v as 'ok' | 'ng')}
          options={[
            { id: 'ok', label: 'OK' },
            { id: 'ng', label: 'NG' },
          ]}
        />
        <div className='grid gap-1'>
          <Label htmlFor='pm-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='pm-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button disabled={!plan || m.isPending} onClick={() => m.mutate()}>
            {t('mes.eqp.pmDone')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
