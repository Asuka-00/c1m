/** NCR / MRB：批次行“登记 NCR”、NCR 详情面板（提案、逐级审批、取消）。 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { Check, FileWarning, Send, X } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import type { MesRow } from '@/lib/api/mes/common'
import { semiApi } from '@/lib/api/mes/semi'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { IconButton } from '@/components/icon-button'
import { enumLabel } from '@/features/mes/common/labels'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { RefSelect } from '@/features/mes/common/ref-select'
import { mesErrorMessage } from '@/features/mes/common/required'
import { Pick } from '../shared/exec-parts'

const SEVERITIES = ['minor', 'major', 'critical']
const DISPOSITIONS = [
  'release',
  'use_as_is',
  'rework',
  'scrap',
  'downgrade',
  'rtv',
]

function useDone() {
  const qc = useQueryClient()
  return (msg: string) => {
    toast.success(msg)
    qc.invalidateQueries({ queryKey: ['mes'] })
  }
}

/** 批次行操作：登记 NCR（默认同时 Hold 批次）。 */
export function RaiseNcr({ row }: { row: MesRow }) {
  const can = useMesCan()
  const done = useDone()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [severity, setSeverity] = useState('major')
  const [desc, setDesc] = useState('')
  const [hold, setHold] = useState(true)
  const m = useMutation({
    mutationFn: () =>
      semiApi.ncrCreate({
        lot_id: row.id,
        title: title.trim(),
        severity,
        description: desc.trim() || undefined,
        hold,
      }),
    onSuccess: (r) => {
      done(t('mes.semi.ncrRaised', { code: r.ncr.code }))
      setOpen(false)
      setTitle('')
      setDesc('')
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  if (!can(MES_PERM.ncrWrite)) return null
  return (
    <>
      <IconButton
        label={t('mes.semi.raiseNcr')}
        variant='ghost'
        onClick={() => setOpen(true)}
      >
        <FileWarning className='size-4' />
      </IconButton>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('mes.semi.raiseNcr')} · {String(row.code)}
            </DialogTitle>
          </DialogHeader>
          <div className='space-y-3'>
            <div className='grid gap-1'>
              <Label htmlFor='ncr-title'>
                {t('mes.field.ncr.title')}
                <span className='text-destructive'> *</span>
              </Label>
              <Input
                id='ncr-title'
                maxLength={200}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>
            <Pick
              id='ncr-severity'
              label={t('mes.field.ncr.severity')}
              none={false}
              value={severity}
              onChange={setSeverity}
              options={SEVERITIES.map((s) => ({
                id: s,
                label: enumLabel('severity', s),
              }))}
            />
            <div className='grid gap-1'>
              <Label htmlFor='ncr-desc'>{t('mes.field.ncr.description')}</Label>
              <Textarea
                id='ncr-desc'
                rows={3}
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
              />
            </div>
            <Label className='flex items-center gap-2'>
              <Checkbox
                checked={hold}
                onCheckedChange={(v) => setHold(v === true)}
              />
              {t('mes.semi.holdLot')}
            </Label>
          </div>
          <DialogFooter>
            <Button
              disabled={!title.trim() || m.isPending}
              onClick={() => m.mutate()}
            >
              {t('mes.semi.raiseNcr')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

/** NCR 详情面板：当前处置、审批记录与可执行操作。 */
export function NcrPanel({ row }: { row: MesRow }) {
  const tk = useTenantKey()
  const can = useMesCan()
  const done = useDone()
  const [disp, setDisp] = useState('release')
  const [scrap, setScrap] = useState<{ id: string; code: string } | null>(null)
  const [comment, setComment] = useState('')
  const q = useQuery({
    queryKey: ['mes', 'ncr', tk, row.id],
    queryFn: () => semiApi.ncrDetail(row.id),
  })
  const onError = (e: unknown) => toast.error(mesErrorMessage(e, undefined))
  const after = (msg: string) => {
    setComment('')
    done(msg)
  }
  const propose = useMutation({
    mutationFn: () =>
      semiApi.ncrPropose(row.id, {
        disposition: disp,
        comment: comment.trim() || undefined,
        scrap_reason_id: disp === 'scrap' ? scrap?.id : undefined,
      }),
    onSuccess: () => after(t('mes.semi.proposed')),
    onError,
  })
  const decide = useMutation({
    mutationFn: (decision: 'approve' | 'reject') =>
      semiApi.ncrApprove(row.id, {
        decision,
        comment: comment.trim() || undefined,
      }),
    onSuccess: (r) =>
      after(t(`mes.semi.ncrStatus.${String(r.ncr.ncr_status)}`)),
    onError,
  })
  const cancel = useMutation({
    mutationFn: () => semiApi.ncrCancel(row.id, comment.trim() || undefined),
    onSuccess: () => after(t('mes.semi.ncrStatus.cancelled')),
    onError,
  })
  const d = q.data
  if (!d) return null
  const n = d.ncr
  const status = String(n.ncr_status)
  const busy = propose.isPending || decide.isPending || cancel.isPending
  const canWrite = can(MES_PERM.ncrWrite)
  return (
    <div className='space-y-4 text-sm'>
      <div className='flex flex-wrap items-center gap-2'>
        <Badge>{enumLabel('ncr_status', status)}</Badge>
        <Badge variant='outline'>
          {enumLabel('severity', String(n.severity))}
        </Badge>
        {n.disposition ? (
          <Badge variant='secondary'>
            {enumLabel('ncr_disposition', String(n.disposition))}
          </Badge>
        ) : null}
        <span className='text-muted-foreground'>
          {t('mes.semi.levels', {
            done: n.approved_levels ?? 0,
            need: n.required_levels ?? 1,
          })}
        </span>
        {d.hold_active && (
          <Badge variant='destructive'>{t('mes.exec.onHold')}</Badge>
        )}
      </div>
      {d.approvals.length > 0 && (
        <ul className='divide-y rounded-md border'>
          {d.approvals.map((a) => (
            <li key={a.id} className='flex flex-wrap gap-2 px-3 py-2'>
              <span className='tabular-nums'>L{String(a.level)}</span>
              <span>{enumLabel('ncr_decision', String(a.decision))}</span>
              <span className='text-muted-foreground'>
                {String(a.username)}
              </span>
              {a.comment ? <span>{String(a.comment)}</span> : null}
              <span className='ms-auto text-xs text-muted-foreground'>
                {a.at ? fmtDateTime(String(a.at)) : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
      {status === 'open' && canWrite && (
        <div className='space-y-2'>
          <Pick
            id='ncr-disp'
            label={t('mes.field.ncr.disposition')}
            none={false}
            value={disp}
            onChange={setDisp}
            options={DISPOSITIONS.map((v) => ({
              id: v,
              label: enumLabel('ncr_disposition', v),
            }))}
          />
          {disp === 'scrap' && (
            <div className='grid gap-1'>
              <Label htmlFor='ncr-scrap'>
                {t('mes.field.ncr.scrap_reason')}
              </Label>
              <RefSelect
                id='ncr-scrap'
                target='reason_code'
                value={scrap?.id ?? null}
                label={scrap?.code ?? null}
                filters={{ reason_type: 'scrap' }}
                onChange={(v, l) =>
                  setScrap(v ? { id: v, code: l ?? '' } : null)
                }
              />
            </div>
          )}
        </div>
      )}
      {(status === 'open' || status === 'reviewing') && (
        <div className='grid gap-1'>
          <Label htmlFor='ncr-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='ncr-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
      )}
      <div className='flex flex-wrap gap-2'>
        {status === 'open' && canWrite && (
          <Button disabled={busy} onClick={() => propose.mutate()}>
            <Send className='size-4' />
            {t('mes.semi.propose')}
          </Button>
        )}
        {status === 'reviewing' && can(MES_PERM.ncrApprove) && (
          <>
            <Button disabled={busy} onClick={() => decide.mutate('approve')}>
              <Check className='size-4' />
              {enumLabel('ncr_decision', 'approve')}
            </Button>
            <Button
              variant='outline'
              disabled={busy || !comment.trim()}
              onClick={() => decide.mutate('reject')}
            >
              {enumLabel('ncr_decision', 'reject')}
            </Button>
          </>
        )}
        {(status === 'open' || status === 'reviewing') && canWrite && (
          <Button
            variant='ghost'
            disabled={busy}
            onClick={() => cancel.mutate()}
          >
            <X className='size-4' />
            {t('mes.semi.cancelNcr')}
          </Button>
        )}
      </div>
    </div>
  )
}
