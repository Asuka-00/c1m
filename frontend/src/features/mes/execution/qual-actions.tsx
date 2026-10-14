/**
 * 人员资质行操作（P3-F2 / B6 40e4342 / D88）：停用、改有效期、恢复启用。
 * 都走通用 CRUD PATCH /mes/operator-qual/{id} 并带 Idempotency-Key；
 * 停用要 reason_id + comment，改有效期（延长、缩短、改为永久都算）要 reason_id + comment + approved_by。
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { CalendarClock, PauseCircle, PlayCircle } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { QUAL_COMMENT_MAX } from '@/lib/api/mes/qual-history'
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
import { IconButton } from '@/components/icon-button'
import { useOperationKey } from '@/features/mes/common/idem-key'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'
import {
  qualActionErrors,
  qualActionBody,
  qualExpiresUnchanged,
  type QualOp,
} from './qual-action-rules'
import { qualReasonMessage } from './qual-history-format'

export function QualActions({ row }: { row: MesRow }) {
  const { entity } = useMesEntity('operator_qual')
  const [op, setOp] = useState<QualOp | null>(null)
  if (!entity?.can_write) return null
  const active = row.is_active !== false
  return (
    <>
      {active ? (
        <>
          <IconButton
            label={t('mes.qualAction.renew')}
            variant='ghost'
            onClick={() => setOp('renew')}
            data-testid='qual-act-renew'
          >
            <CalendarClock className='size-4' />
          </IconButton>
          <IconButton
            label={t('mes.qualAction.deactivate')}
            variant='ghost'
            onClick={() => setOp('deactivate')}
            data-testid='qual-act-deactivate'
          >
            <PauseCircle className='size-4' />
          </IconButton>
        </>
      ) : (
        <IconButton
          label={t('mes.qualAction.reactivate')}
          variant='ghost'
          onClick={() => setOp('reactivate')}
          data-testid='qual-act-reactivate'
        >
          <PlayCircle className='size-4' />
        </IconButton>
      )}
      <Dialog open={op != null} onOpenChange={(o) => !o && setOp(null)}>
        {op && <Body row={row} op={op} onClose={() => setOp(null)} />}
      </Dialog>
    </>
  )
}

function Body({
  row,
  op,
  onClose,
}: {
  row: MesRow
  op: QualOp
  onClose: () => void
}) {
  const qc = useQueryClient()
  const tk = useTenantKey()
  const key = useOperationKey()
  const [v, setV] = useState({
    expires_on: String(row.expires_on ?? ''),
    reason_id: '',
    comment: '',
    approved_by: '',
  })
  const [tried, setTried] = useState(false)
  const reasons = useQuery({
    queryKey: ['mes', 'reason_code', 'operator_qual', tk],
    queryFn: () =>
      mesApi.list('reason_code', {
        reason_type: 'operator_qual',
        page_size: 100,
      }),
    enabled: op !== 'reactivate',
  })
  const errs = qualActionErrors(op, v)
  const unchanged =
    op === 'renew' && qualExpiresUnchanged(row.expires_on, v.expires_on)
  const m = useMutation({
    mutationFn: () => {
      const body = qualActionBody(op, v)
      return mesApi.update(
        'operator_qual',
        String(row.id),
        body,
        key.key(`${op}:${row.id}:${JSON.stringify(body)}`)
      )
    },
    onSuccess: () => {
      key.done()
      toast.success(t('mes.saved'))
      qc.invalidateQueries({ queryKey: ['mes', 'operator_qual'] })
      onClose()
    },
    onError: (e) =>
      toast.error(qualReasonMessage(e) || mesErrorMessage(e, undefined)),
  })
  const err = (k: keyof typeof v) =>
    tried && errs[k] ? (
      <p className='text-sm text-destructive' role='alert'>
        {errs[k]}
      </p>
    ) : null
  return (
    <DialogContent data-testid='qual-action-dialog'>
      <DialogHeader>
        <DialogTitle>{t(`mes.qualAction.${op}`)}</DialogTitle>
        <DialogDescription>{t(`mes.qualAction.${op}Desc`)}</DialogDescription>
      </DialogHeader>
      {op !== 'reactivate' && (
        <div className='flex flex-col gap-3'>
          {op === 'renew' && (
            <div className='flex flex-col gap-1'>
              <Label htmlFor='qa-exp' title={t('mes.qualAction.expiresTip')}>
                {t('mes.qualHistory.field.expires_on')}
              </Label>
              <Input
                id='qa-exp'
                type='date'
                value={v.expires_on}
                title={t('mes.qualAction.expiresTip')}
                onChange={(e) => setV({ ...v, expires_on: e.target.value })}
              />
              {unchanged && (
                <p
                  className='text-sm text-muted-foreground'
                  data-testid='qual-expires-unchanged'
                >
                  {t('mes.qualAction.expiresUnchanged')}
                </p>
              )}
            </div>
          )}
          <div className='flex flex-col gap-1'>
            <Label htmlFor='qa-reason'>
              {t('mes.qualHistory.col.reasonId')} *
            </Label>
            <select
              id='qa-reason'
              className='h-9 rounded-md border border-input bg-transparent px-2 text-sm'
              value={v.reason_id}
              title={t('mes.qualAction.reasonTip')}
              onChange={(e) => setV({ ...v, reason_id: e.target.value })}
            >
              <option value=''>—</option>
              {(reasons.data?.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {String(r.code)} {r.name ? `· ${String(r.name)}` : ''}
                </option>
              ))}
            </select>
            {err('reason_id')}
          </div>
          <div className='flex flex-col gap-1'>
            <Label htmlFor='qa-comment'>
              {t('mes.qualHistory.col.comment')} *
            </Label>
            <Textarea
              id='qa-comment'
              value={v.comment}
              maxLength={QUAL_COMMENT_MAX}
              onChange={(e) => setV({ ...v, comment: e.target.value })}
            />
            {err('comment')}
          </div>
          {op === 'renew' && (
            <div className='flex flex-col gap-1'>
              <Label
                htmlFor='qa-approver'
                title={t('mes.qualAction.approverTip')}
              >
                {t('mes.qualHistory.col.approvedBy')} *
              </Label>
              <Input
                id='qa-approver'
                value={v.approved_by}
                title={t('mes.qualAction.approverTip')}
                onChange={(e) => setV({ ...v, approved_by: e.target.value })}
              />
              {err('approved_by')}
            </div>
          )}
        </div>
      )}
      <DialogFooter>
        <Button variant='outline' onClick={onClose}>
          {t('common.cancel')}
        </Button>
        <Button
          disabled={m.isPending || unchanged}
          title={unchanged ? t('mes.qualAction.expiresUnchanged') : undefined}
          data-testid='qual-action-submit'
          onClick={() => {
            setTried(true)
            if (Object.keys(errs).length === 0) m.mutate()
          }}
        >
          {t('common.save')}
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
