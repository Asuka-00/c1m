/** 交接班日志页面：按班次登记交接事项与未结事项，接班人确认。 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { CheckCheck, NotebookPen } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import { shiftLogApi, type ShiftLog } from '@/lib/api/mes/shift-log'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  ConfirmDialog,
  DataTable,
  Page,
  clientList,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'
import { Pick } from '../shared/exec-parts'
import { DateRange } from './report-parts'
import { isoDay } from './report-utils'

/** 交接班日志。 */
export default function ShiftHandover() {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const { entity } = useMesEntity('shift_log')
  const canWrite = useMesCan()(MES_PERM.execWrite)
  const [from, setFrom] = useState(isoDay(-6))
  const [to, setTo] = useState(isoDay())
  const [creating, setCreating] = useState(false)
  const [ack, setAck] = useState<ShiftLog | null>(null)
  const [comment, setComment] = useState('')
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'shift-logs', from, to],
    queryFn: () => shiftLogApi.list({ date_from: from, date_to: to }),
  })
  const all = useMemo(() => q.data ?? [], [q.data])
  const filters: FilterDef[] = [
    { type: 'text', name: 'q', placeholder: t('mes.shiftLog.search') },
    {
      type: 'select',
      name: 'log_status',
      label: t('mes.shiftLog.allStatus'),
      options: (['open', 'acknowledged'] as const).map((v) => ({
        value: v,
        label: t(`mes.shiftLog.status.${v}`),
      })),
    },
    {
      type: 'select',
      name: 'shift',
      label: t('mes.shiftLog.allShifts'),
      options: [...new Set(all.map((r) => r.shift ?? ''))]
        .filter(Boolean)
        .map((v) => ({ value: v, label: v })),
    },
  ]
  const lp = useListParams(filters)
  const view = clientList(all, lp, {
    text: (r) => `${r.summary} ${r.open_items ?? ''} ${r.handed_by ?? ''}`,
  })
  const doAck = useMutation({
    mutationFn: () => shiftLogApi.ack(ack!.id, comment || undefined),
    onSuccess: () => {
      toast.success(t('mes.shiftLog.acked'))
      setAck(null)
      setComment('')
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => toast.error(mesErrorMessage(e, entity)),
  })
  return (
    <Page
      title={t('menu.mes-shift-handover')}
      description={t('mes.shiftLog.hint')}
    >
      <div className='flex flex-wrap items-end gap-3'>
        <DateRange from={from} to={to} setFrom={setFrom} setTo={setTo} />
        {canWrite && (
          <Button onClick={() => setCreating(true)} data-testid='new-handover'>
            <NotebookPen className='size-4' />
            {t('mes.shiftLog.new')}
          </Button>
        )}
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
            header: t('mes.shiftLog.date'),
            sortKey: 'shift_date',
            cell: (r) => (
              <span className='whitespace-nowrap'>
                {r.shift_date} {r.shift_name ?? r.shift}
                {r.area ? ` · ${r.area}` : ''}
              </span>
            ),
          },
          {
            header: t('mes.shiftLog.summary'),
            cell: (r) => <div className='whitespace-pre-wrap'>{r.summary}</div>,
          },
          {
            header: t('mes.shiftLog.openItems'),
            cell: (r) => (
              <div className='whitespace-pre-wrap text-amber-700 dark:text-amber-400'>
                {r.open_items ?? '—'}
              </div>
            ),
          },
          { header: t('mes.shiftLog.handedBy'), cell: (r) => r.handed_by },
          {
            header: t('mes.shiftLog.statusCol'),
            cell: (r) =>
              r.log_status === 'open' ? (
                <Badge className='bg-amber-500 text-white'>
                  {t('mes.shiftLog.status.open')}
                </Badge>
              ) : (
                <span title={r.receive_comment ?? undefined}>
                  <Badge variant='outline'>
                    {t('mes.shiftLog.status.acknowledged')}
                  </Badge>{' '}
                  {r.received_by}
                </span>
              ),
          },
          {
            header: '',
            cell: (r) =>
              canWrite &&
              r.log_status === 'open' && (
                <Button size='sm' variant='outline' onClick={() => setAck(r)}>
                  <CheckCheck className='size-4' />
                  {t('mes.shiftLog.ack')}
                </Button>
              ),
          },
        ]}
      />
      <HandoverDialog open={creating} onOpenChange={setCreating} />
      <ConfirmDialog
        open={!!ack}
        onOpenChange={(o) => !o && setAck(null)}
        title={t('mes.shiftLog.ack')}
        desc={t('mes.shiftLog.ackDesc')}
        confirmText={t('mes.shiftLog.ack')}
        handleConfirm={() => doAck.mutate()}
      >
        <Textarea
          rows={2}
          aria-label={t('mes.shiftLog.ackComment')}
          placeholder={t('mes.shiftLog.ackComment')}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </ConfirmDialog>
    </Page>
  )
}

/** 交班对话框：日期、班次、区域、交接事项、未结事项。 */
function HandoverDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
}) {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const { entity } = useMesEntity('shift_log')
  const [day, setDay] = useState(isoDay())
  const [shift, setShift] = useState('')
  const [area, setArea] = useState('')
  const [summary, setSummary] = useState('')
  const [items, setItems] = useState('')
  const refs = useQuery({
    queryKey: ['mes', 'shift-refs', tk],
    queryFn: async () => ({
      shifts: (await mesApi.list('shift', { page_size: 100 })).data,
      areas: (await mesApi.list('area', { page_size: 200 })).data,
    }),
    enabled: open,
  })
  const m = useMutation({
    mutationFn: () =>
      shiftLogApi.create({
        shift_date: day,
        shift_id: shift,
        area_id: area || undefined,
        summary,
        open_items: items || undefined,
      }),
    onSuccess: () => {
      toast.success(t('mes.shiftLog.created'))
      onOpenChange(false)
      setSummary('')
      setItems('')
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => toast.error(mesErrorMessage(e, entity)),
  })
  const opt = (r: { id: string; code?: unknown; name?: unknown }) => ({
    id: r.id,
    label: `${String(r.code)} · ${String(r.name)}`,
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('mes.shiftLog.new')}</DialogTitle>
          <DialogDescription>{t('mes.shiftLog.newDesc')}</DialogDescription>
        </DialogHeader>
        <div className='grid gap-1'>
          <Label htmlFor='ho-date'>{t('mes.shiftLog.date')}</Label>
          <Input
            id='ho-date'
            type='date'
            value={day}
            onChange={(e) => setDay(e.target.value)}
          />
        </div>
        <Pick
          id='ho-shift'
          label={t('mes.shiftLog.shift')}
          required
          none={false}
          value={shift}
          onChange={setShift}
          options={(refs.data?.shifts ?? []).map(opt)}
        />
        <Pick
          id='ho-area'
          label={t('mes.shiftLog.area')}
          value={area}
          onChange={setArea}
          options={(refs.data?.areas ?? []).map(opt)}
        />
        <div className='grid gap-1'>
          <Label htmlFor='ho-summary'>
            {t('mes.shiftLog.summary')}
            <span className='text-destructive'> *</span>
          </Label>
          <Textarea
            id='ho-summary'
            rows={3}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
          />
        </div>
        <div className='grid gap-1'>
          <Label htmlFor='ho-items'>{t('mes.shiftLog.openItems')}</Label>
          <Textarea
            id='ho-items'
            rows={2}
            value={items}
            onChange={(e) => setItems(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            disabled={!shift || !summary.trim() || !day || m.isPending}
            onClick={() => m.mutate()}
          >
            {t('mes.shiftLog.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
