/** 设备报警履历的清除操作（B9：POST /mes/eqp/alarms/{id}/clear）。 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { BellOff } from 'lucide-react'
import { toast } from 'sonner'
import type { MesRow } from '@/lib/api/mes/common'
import { eqpApi } from '@/lib/api/mes/equipment'
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
import { IconButton } from '@/components/icon-button'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { mesErrorMessage } from '@/features/mes/common/required'

/** 报警中且有 `mes.alarm:write` 时显示清除按钮；清除不恢复 Hold / 设备状态。 */
export function AlarmClearButton({ row }: { row: MesRow }) {
  const can = useMesCan()
  const [open, setOpen] = useState(false)
  const [comment, setComment] = useState('')
  const qc = useQueryClient()
  const m = useMutation({
    mutationFn: () =>
      eqpApi.alarmClear(String(row.id), {
        ...(comment.trim() ? { comment: comment.trim() } : {}),
      }),
    onSuccess: (r) => {
      if (r.cleared) toast.success(t('mes.alarm.cleared'))
      else toast.info(t('mes.alarm.already'))
      setOpen(false)
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  if (row.alarm_status !== 'active' || !can(MES_PERM.alarmWrite)) return null
  return (
    <>
      <IconButton
        label={t('mes.alarm.clear')}
        variant='ghost'
        onClick={() => setOpen(true)}
        data-testid='alarm-clear'
      >
        <BellOff className='size-4' />
      </IconButton>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('mes.alarm.clear')} · {String(row.alid ?? '')}
            </DialogTitle>
            <DialogDescription>{t('mes.alarm.clearDesc')}</DialogDescription>
          </DialogHeader>
          <div className='grid gap-1'>
            <Label htmlFor='alarm-clear-comment'>{t('mes.exec.comment')}</Label>
            <Textarea
              id='alarm-clear-comment'
              rows={2}
              maxLength={300}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button
              disabled={m.isPending}
              onClick={() => m.mutate()}
              data-testid='alarm-clear-ok'
            >
              {t('mes.alarm.clear')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
