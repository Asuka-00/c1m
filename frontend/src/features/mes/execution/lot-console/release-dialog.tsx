import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
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
import { reasonOptLabel } from '@/features/mes/common/labels'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'
import { Pick } from '../shared/exec-parts'

/**
 * 释放 Hold 对话框（操作台 / Hold 管理共用，单条与批量）：释放原因代码 + 备注。
 * 单条走逐条释放接口（错误定位到字段），多条走批量接口（逐条成功 / 失败汇总）。
 */
export function ReleaseDialog({
  ids,
  lots,
  onClose,
}: {
  ids: string[]
  lots: string[]
  onClose: (done: boolean) => void
}) {
  const qc = useQueryClient()
  const tk = useTenantKey()
  const { entity } = useMesEntity('lot_hold')
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const reasons = useQuery({
    queryKey: ['mes', 'reason_code', 'release-options', tk],
    queryFn: () =>
      mesApi.list('reason_code', { reason_type: 'release', page_size: 100 }),
  })
  const single = ids.length === 1
  const m = useMutation({
    mutationFn: async () => {
      if (single) {
        await execApi.release(ids[0], reason, comment || undefined)
        toast.success(t('mes.exec.released'))
        return
      }
      const r = await execApi.releaseBatch({
        hold_ids: ids,
        reason_id: reason,
        comment: comment || undefined,
      })
      const msg = t('mes.holdrel.released', {
        ok: r.released.length,
        bad: r.failed.length,
      })
      if (r.failed.length) toast.warning(msg)
      else toast.success(msg)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mes'] })
      onClose(true)
    },
    onError: (e) => toast.error(mesErrorMessage(e, entity)),
  })
  const title = single ? t('mes.exec.release') : t('mes.holdrel.release')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {single
              ? lots.join(', ')
              : t('mes.holdrel.selected', { n: ids.length })}
          </DialogDescription>
        </DialogHeader>
        <Pick
          id='release-reason'
          label={t('mes.exec.releaseReason')}
          required
          none={false}
          value={reason}
          onChange={setReason}
          options={(reasons.data?.data ?? []).map((r) => ({
            id: String(r.id),
            label: reasonOptLabel(r as { code: string; name?: string }),
          }))}
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
          <Button
            disabled={!reason || m.isPending}
            onClick={() => m.mutate()}
            data-testid='confirm-release'
          >
            {title}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
