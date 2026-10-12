/** 设备状态看板：E10 当前状态、PM 到期、停机标记；支持手动改状态与登记 PM 完成。 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import { eqpApi, type BoardRow } from '@/lib/api/mes/equipment'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/crud'
import { optLabel } from '@/features/mes/common/labels'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesMeta } from '@/features/mes/common/use-mes-meta'
import { Pick } from '@/features/mes/execution/exec-parts'

const PAGE = 20

/** 设备状态看板页面。 */
export default function EqpBoard() {
  const tk = useTenantKey()
  const { data: meta } = useMesMeta()
  const can = (p: string) => (meta?.perms ?? []).includes(p)
  const [page, setPage] = useState(0)
  const [dlg, setDlg] = useState<{ kind: 'e10' | 'pm'; row: BoardRow } | null>(
    null
  )
  const q = useQuery({
    queryKey: ['mes', 'eqp', tk, 'board'],
    queryFn: eqpApi.board,
    refetchInterval: 60_000,
  })
  const rows = q.data ?? []
  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const view = rows.slice(page * PAGE, page * PAGE + PAGE)
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
      <div className='rounded-md border'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('mes.eqp.code')}</TableHead>
              <TableHead>{t('mes.eqp.name')}</TableHead>
              <TableHead>{t('mes.eqp.state')}</TableHead>
              <TableHead>{t('mes.eqp.pm')}</TableHead>
              <TableHead className='text-right'>
                {t('mes.eqp.actions')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {view.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className='h-20 text-center text-muted-foreground'
                >
                  {q.isLoading ? t('common.loading') : t('common.noResults')}
                </TableCell>
              </TableRow>
            )}
            {view.map((r) => (
              <TableRow key={r.id}>
                <TableCell className='font-mono'>{r.code}</TableCell>
                <TableCell>{r.name}</TableCell>
                <TableCell>
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
                </TableCell>
                <TableCell className='space-x-1'>
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
                </TableCell>
                <TableCell className='space-x-2 text-right'>
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
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className='mt-3 flex items-center justify-end gap-2 text-sm'>
        <span className='text-muted-foreground'>
          {t('common.total', { count: rows.length })}
        </span>
        <Button
          size='sm'
          variant='outline'
          disabled={page === 0}
          onClick={() => setPage(page - 1)}
        >
          ‹
        </Button>
        <span>
          {page + 1} / {pages}
        </span>
        <Button
          size='sm'
          variant='outline'
          disabled={page + 1 >= pages}
          onClick={() => setPage(page + 1)}
        >
          ›
        </Button>
      </div>
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
