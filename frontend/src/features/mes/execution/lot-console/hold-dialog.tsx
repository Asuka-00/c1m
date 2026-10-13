/** Hold 批次对话框（选择 Hold 原因并填写备注）。 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { toast } from 'sonner'
import { execApi, type ExecContext } from '@/lib/api/mes/execution'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { optLabel } from '@/features/mes/common/labels'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'
import { Pick } from '../exec-parts'

export function HoldDialog({
  cx,
  open,
  onOpenChange,
}: {
  cx: ExecContext
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const { entity } = useMesEntity('lot_hold')
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const m = useMutation({
    mutationFn: () =>
      execApi.hold(String(cx.lot.id), reason, comment || undefined),
    onSuccess: () => {
      toast.success(t('mes.exec.held'))
      onOpenChange(false)
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => toast.error(mesErrorMessage(e, entity)),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('mes.exec.hold')} · {String(cx.lot.code)}
          </DialogTitle>
        </DialogHeader>
        <Pick
          id='hold-reason'
          label={t('mes.exec.reason')}
          required
          none={false}
          value={reason}
          onChange={setReason}
          options={cx.reasons.hold.map((r) => ({
            id: r.id,
            label: optLabel(r),
          }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='hold-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='hold-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button disabled={!reason || m.isPending} onClick={() => m.mutate()}>
            {t('mes.exec.hold')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
