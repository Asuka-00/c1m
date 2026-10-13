import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { toast } from 'sonner'
import { execApi } from '@/lib/api/mes/execution'
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
import { optLabel } from '@/features/mes/common/labels'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'
import { Pick } from '../exec-parts'

/** 释放 Hold 对话框（选择原因代码并填写备注）。 */
export function ReleaseDialog({
  hold,
  reasons,
  open,
  onOpenChange,
}: {
  hold: Record<string, unknown>
  reasons: { id: string; code: string; name?: string }[]
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const { entity } = useMesEntity('lot_hold')
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const m = useMutation({
    mutationFn: () =>
      execApi.release(String(hold.id), reason || null, comment || undefined),
    onSuccess: () => {
      toast.success(t('mes.exec.released'))
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
            {t('mes.exec.release')} · {String(hold.lot_label ?? '')}
          </DialogTitle>
          <DialogDescription>
            {String(hold.reason_label ?? '')}
          </DialogDescription>
        </DialogHeader>
        <Pick
          id='release-reason'
          label={t('mes.exec.releaseReason')}
          value={reason}
          onChange={setReason}
          options={reasons.map((r) => ({ id: r.id, label: optLabel(r) }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='release-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='release-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button disabled={m.isPending} onClick={() => m.mutate()}>
            {t('mes.exec.release')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
