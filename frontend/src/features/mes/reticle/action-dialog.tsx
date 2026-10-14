/** 光罩动作对话框（usage / hold / release / restore / 清洗 / 维修 / 检查 / scrap / life-reset）。 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { toast } from 'sonner'
import {
  reticleApi,
  type Reticle,
  type ReticleAction,
  type ReticleActionInput,
} from '@/lib/api/mes/reticle'
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
import { newEventId } from '@/features/mes/common/event-id'
import {
  ACTIONS,
  TEXT_MAX,
  actionLabel,
  reticleErrorMessage,
  validateAction,
} from './reticle-rules'

function FieldErr({ msg }: { msg?: string }) {
  return msg ? <p className='text-sm text-destructive'>{msg}</p> : null
}

/** 对话框本体；`action` 为空时关闭。 */
export function ReticleActionDialog({
  reticle,
  action,
  onClose,
}: {
  reticle: Reticle
  action: ReticleAction | null
  onClose: () => void
}) {
  return (
    <Dialog open={action != null} onOpenChange={(o) => !o && onClose()}>
      {action && (
        <Body
          key={action}
          reticle={reticle}
          action={action}
          onClose={onClose}
        />
      )}
    </Dialog>
  )
}

function Body({
  reticle,
  action,
  onClose,
}: {
  reticle: Reticle
  action: ReticleAction
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [v, setV] = useState<ReticleActionInput>(
    action === 'inspection' ? { disposition: 'none' } : {}
  )
  const [errs, setErrs] = useState<Record<string, string>>({})
  // 同一次提交（含失败后重试）用同一个 Idempotency-Key；成功后关闭对话框
  const [key] = useState(newEventId)
  const fields = ACTIONS[action].fields
  const m = useMutation({
    mutationFn: () =>
      reticleApi.act(
        reticle.id,
        action,
        {
          ...v,
          defect_count:
            String(v.defect_count ?? '').trim() === ''
              ? undefined
              : Number(v.defect_count),
        },
        key
      ),
    onSuccess: () => {
      toast.success(t('mes.reticle.done', { action: actionLabel(action) }))
      qc.invalidateQueries({ queryKey: ['mes', 'reticle'] })
      onClose()
    },
    onError: (e) => toast.error(reticleErrorMessage(e, action)),
  })
  const set = (k: keyof ReticleActionInput) => (s: string) =>
    setV((o) => ({ ...o, [k]: s }))
  const submit = () => {
    const e = validateAction(action, v)
    setErrs(e)
    if (Object.keys(e).length === 0) m.mutate()
  }
  const text = (k: 'reason' | 'comment' | 'note', required: boolean) => (
    <div className='grid gap-1'>
      <Label htmlFor={`reticle-${k}`}>
        {t(`mes.reticle.field.${k}`)}
        {required ? ' *' : ''}
      </Label>
      <Textarea
        id={`reticle-${k}`}
        data-testid={`reticle-${k}`}
        rows={2}
        maxLength={TEXT_MAX}
        value={v[k] ?? ''}
        onChange={(e) => set(k)(e.target.value)}
      />
      <FieldErr msg={errs[k]} />
    </div>
  )
  const sel = (
    k: 'kind' | 'result' | 'disposition',
    opts: string[],
    ns: string,
    required: boolean
  ) => (
    <div className='grid gap-1'>
      <Label htmlFor={`reticle-${k}`}>
        {t(`mes.reticle.field.${k}`)}
        {required ? ' *' : ''}
      </Label>
      <select
        id={`reticle-${k}`}
        data-testid={`reticle-${k}`}
        className='h-9 rounded-md border border-input bg-transparent px-2 text-sm'
        value={v[k] ?? ''}
        onChange={(e) => set(k)(e.target.value)}
      >
        <option value=''>—</option>
        {opts.map((o) => (
          <option key={o} value={o}>
            {t(`mes.reticle.${ns}.${o}`)}
          </option>
        ))}
      </select>
      <FieldErr msg={errs[k]} />
    </div>
  )
  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>
          {t(`mes.reticle.action.${action}`)} · {reticle.code}
        </DialogTitle>
        <DialogDescription>
          {t(`mes.reticle.actionDesc.${action}`)}
        </DialogDescription>
      </DialogHeader>
      <div className='grid gap-3'>
        {fields.includes('delta') && (
          <>
            <div className='grid gap-1'>
              <Label htmlFor='reticle-delta'>
                {t('mes.reticle.field.delta')} *
              </Label>
              <Input
                id='reticle-delta'
                data-testid='reticle-delta'
                inputMode='decimal'
                value={String(v.delta ?? '')}
                onChange={(e) => set('delta')(e.target.value)}
              />
              <FieldErr msg={errs.delta} />
            </div>
            <div className='grid gap-1'>
              <Label htmlFor='reticle-reason-id'>
                {t('mes.reticle.field.reason_id')}
              </Label>
              <Input
                id='reticle-reason-id'
                data-testid='reticle-reason-id'
                value={v.reason_id ?? ''}
                onChange={(e) => set('reason_id')(e.target.value)}
              />
              <FieldErr msg={errs.reason_id} />
            </div>
            {text('note', false)}
          </>
        )}
        {fields.includes('inspection') && (
          <>
            {sel('kind', ['particle', 'haze', 'cd', 'other'], 'inspKind', true)}
            {sel('result', ['pass', 'fail'], 'result', true)}
            <div className='grid gap-1'>
              <Label htmlFor='reticle-defect_count'>
                {t('mes.reticle.col.defects')}
              </Label>
              <Input
                id='reticle-defect_count'
                data-testid='reticle-defect_count'
                inputMode='numeric'
                value={String(v.defect_count ?? '')}
                onChange={(e) => set('defect_count')(e.target.value)}
              />
              <FieldErr msg={errs.defect_count} />
            </div>
            {sel(
              'disposition',
              ['none', 'clean', 'hold', 'repair', 'scrap'],
              'disposition',
              false
            )}
          </>
        )}
        {fields.includes('reason') && text('reason', true)}
        {fields.includes('comment') && text('comment', false)}
      </div>
      <DialogFooter>
        <Button variant='outline' onClick={onClose}>
          {t('common.cancel')}
        </Button>
        <Button
          disabled={m.isPending}
          onClick={submit}
          variant={action === 'scrap' ? 'destructive' : 'default'}
          data-testid='reticle-action-ok'
        >
          {t(`mes.reticle.action.${action}`)}
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
