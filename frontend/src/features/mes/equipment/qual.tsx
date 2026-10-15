/**
 * F5 机台看板：PM 后待 Qual（B6）。
 *
 * 待 Qual 取自 `qual_state`，与 E10 状态分开显示（D33）；有子单元的显示是哪个子单元待 Qual（D35）。
 * 登记 Qual 结果：403 只提示无权限，404 任务不存在，409 `qual_task_closed` 已登记（D34）。
 */
import { useState } from 'react'
import { AxiosError } from 'axios'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { toast } from 'sonner'
import type { BoardRow } from '@/lib/api/mes/equipment'
import { qualApi, type QualTask } from '@/lib/api/mes/qual'
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
import { Pick } from '@/features/mes/execution/exec-parts'
import { isWaitQual, qualError } from './qual-rules'

/** 待 Qual 标记：子单元（若有）与生成时间（UTC → 本地）。 */
export function QualBadge({ row, task }: { row: BoardRow; task?: QualTask }) {
  if (!isWaitQual(row)) return null
  const sub = task?.sub_unit_label
  const title = task?.requested_at
    ? `${t('mes.eqp.qual.requestedAt')}: ${fmtDateTime(task.requested_at)}`
    : undefined
  return (
    <Badge
      variant='secondary'
      className='border-amber-500 bg-amber-100 text-amber-900'
      title={title}
      data-testid={`qual-${row.code}`}
    >
      {sub ? t('mes.eqp.qual.waitSub', { unit: sub }) : t('mes.eqp.qual.wait')}
    </Badge>
  )
}

/** 登记 Qual 结果对话框。 */
export function QualDialog({
  row,
  task,
  onClose,
}: {
  row: BoardRow
  task?: QualTask
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [result, setResult] = useState<'pass' | 'fail'>('pass')
  const [comment, setComment] = useState('')
  const [err, setErr] = useState('')
  const id = row.qual_task_id ?? ''
  const m = useMutation({
    mutationFn: () =>
      qualApi.record(id, {
        result,
        ...(comment.trim() ? { comment: comment.trim() } : {}),
      }),
    onSuccess: (r) => {
      toast.success(
        r.next_task ? t('mes.eqp.qual.failed') : t('mes.eqp.qual.passed')
      )
      qc.invalidateQueries({ queryKey: ['mes'] })
      onClose()
    },
    onError: (e) => {
      const msg = qualError(e)
      setErr(msg)
      toast.error(msg)
      // 任务已登记 / 不存在：刷新看板，拿到最新的待 Qual 状态
      if (
        e instanceof AxiosError &&
        [404, 409].includes(e.response?.status ?? 0)
      )
        qc.invalidateQueries({ queryKey: ['mes'] })
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('mes.eqp.qual.record')} · {row.code}
          </DialogTitle>
          <DialogDescription>
            {task?.sub_unit_label
              ? t('mes.eqp.qual.descSub', { unit: task.sub_unit_label })
              : t('mes.eqp.qual.desc')}
            {task?.requested_at &&
              ` · ${t('mes.eqp.qual.requestedAt')}: ${fmtDateTime(task.requested_at)}`}
          </DialogDescription>
        </DialogHeader>
        <Pick
          id='qual-result'
          label={t('mes.eqp.result')}
          required
          none={false}
          value={result}
          onChange={(v) => setResult(v as 'pass' | 'fail')}
          options={[
            { id: 'pass', label: t('mes.eqp.qual.pass') },
            { id: 'fail', label: t('mes.eqp.qual.fail') },
          ]}
        />
        <div className='grid gap-1'>
          <Label htmlFor='qual-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='qual-comment'
            rows={2}
            maxLength={300}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        {err && (
          <p role='alert' className='text-sm text-destructive'>
            {err}
          </p>
        )}
        <DialogFooter>
          <Button
            disabled={!id || m.isPending}
            onClick={() => m.mutate()}
            data-testid='qual-submit'
          >
            {t('mes.eqp.qual.record')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
