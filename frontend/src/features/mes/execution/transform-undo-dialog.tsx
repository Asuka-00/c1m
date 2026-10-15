/**
 * 撤销转换对话框（F4-02 / P2）：可选原因码与备注；子批已动过时列出 409 原因，不关闭对话框。
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { TriangleAlert } from 'lucide-react'
import { toast } from 'sonner'
import { execApi } from '@/lib/api/mes/execution'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
import { RefSelect } from '@/features/mes/common/ref-select'
import { undoErrorLines } from './transform-undo'

export function TransformUndoDialog({
  transformId,
  childCodes,
  open,
  onOpenChange,
}: {
  transformId: string
  /** 转换生成的子批编码（提示会删除哪些子批） */
  childCodes: string[]
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const [reason, setReason] = useState<{
    id: string | null
    label: string | null
  }>({ id: null, label: null })
  const [comment, setComment] = useState('')
  const [errs, setErrs] = useState<string[]>([])
  const m = useMutation({
    mutationFn: () =>
      execApi.transformUndo(transformId, {
        ...(reason.id ? { reason_id: reason.id } : {}),
        ...(comment.trim() ? { comment: comment.trim() } : {}),
      }),
    onMutate: () => setErrs([]),
    onSuccess: (r) => {
      toast.success(
        t('mes.tundo.done', { list: r.removed_children.join('、') || '—' })
      )
      onOpenChange(false)
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => setErrs(undoErrorLines(e)),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('mes.tundo.title')}</DialogTitle>
          <DialogDescription>{t('mes.tundo.desc')}</DialogDescription>
        </DialogHeader>
        {childCodes.length > 0 && (
          <p className='text-sm' data-testid='undo-children'>
            {t('mes.tundo.willRemove', { list: childCodes.join('、') })}
          </p>
        )}
        <div className='grid gap-1'>
          <Label>{t('mes.exec.reason')}</Label>
          <RefSelect
            target='reason_code'
            value={reason.id}
            label={reason.label}
            onChange={(id, label) => setReason({ id, label })}
          />
        </div>
        <div className='grid gap-1'>
          <Label htmlFor='undo-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='undo-comment'
            rows={2}
            maxLength={300}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        {errs.length > 0 && (
          <Alert variant='destructive' data-testid='undo-error'>
            <TriangleAlert />
            <AlertDescription>
              <ul className='list-disc ps-4'>
                {errs.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        <DialogFooter>
          <Button
            variant='destructive'
            data-testid='do-undo'
            disabled={m.isPending}
            onClick={() => m.mutate()}
          >
            {t('mes.tundo.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
