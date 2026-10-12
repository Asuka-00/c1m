/** 批次操作台「在制调整」卡片：跳站（Jump）。 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { SkipForward, Wrench } from 'lucide-react'
import { toast } from 'sonner'
import { execApi, type ExecContext } from '@/lib/api/mes/execution'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
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
import { Pick } from './exec-parts'

/** 在制调整卡片：按权限与批次状态提供跳站等操作。 */
export function WipActionsCard({
  cx,
  perms,
}: {
  cx: ExecContext
  perms: string[]
}) {
  const [open, setOpen] = useState<'jump' | null>(null)
  const st = String(cx.lot.lot_status)
  const canJump =
    perms.includes('mes.exec:jump') &&
    st === 'waiting' &&
    !cx.lot.on_hold &&
    (cx.route_steps?.length ?? 0) > 1
  return (
    <Card className='gap-3'>
      <CardHeader>
        <CardTitle className='flex items-center gap-2 text-base'>
          <Wrench className='size-4 text-muted-foreground' />
          {t('mes.wip.title')}
        </CardTitle>
        <CardAction className='flex gap-2'>
          <Button
            size='sm'
            variant='outline'
            disabled={!canJump}
            onClick={() => setOpen('jump')}
            data-testid='open-jump'
          >
            <SkipForward className='size-4' />
            {t('mes.wip.jump')}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className='text-sm text-muted-foreground'>
        {t('mes.wip.hint')}
      </CardContent>
      <JumpDialog
        cx={cx}
        open={open === 'jump'}
        canOverride={perms.includes('mes.exec:override')}
        onOpenChange={(o) => setOpen(o ? 'jump' : null)}
      />
    </Card>
  )
}

/** 跳站对话框：目标工步（同流程）、跳站原因、备注，可选强制放行。 */
function JumpDialog({
  cx,
  open,
  canOverride,
  onOpenChange,
}: {
  cx: ExecContext
  open: boolean
  canOverride: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const { entity } = useMesEntity('lot_history')
  const [to, setTo] = useState('')
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const [override, setOverride] = useState(false)
  const [ovReason, setOvReason] = useState('')
  const m = useMutation({
    mutationFn: () =>
      execApi.jump(String(cx.lot.id), {
        to_step_id: to,
        reason_id: reason,
        comment: comment || undefined,
        override: override || undefined,
        override_reason: override ? ovReason : undefined,
      }),
    onSuccess: () => {
      toast.success(t('mes.wip.jumped'))
      onOpenChange(false)
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => toast.error(mesErrorMessage(e, entity)),
  })
  const steps = (cx.route_steps ?? []).filter((s) => s.id !== cx.step?.id)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('mes.wip.jump')} · {String(cx.lot.code)}
          </DialogTitle>
          <DialogDescription>{t('mes.wip.jumpDesc')}</DialogDescription>
        </DialogHeader>
        <Pick
          id='jump-to'
          label={t('mes.wip.toStep')}
          required
          none={false}
          value={to}
          onChange={setTo}
          options={steps.map((s) => ({
            id: s.id,
            label: `${s.seq} · ${s.operation ?? ''}`,
          }))}
        />
        <Pick
          id='jump-reason'
          label={t('mes.exec.reason')}
          required
          none={false}
          value={reason}
          onChange={setReason}
          options={cx.reasons.jump.map((r) => ({
            id: r.id,
            label: optLabel(r),
          }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='jump-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='jump-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        {canOverride && (
          <div className='grid gap-2'>
            <Label className='flex items-center gap-2'>
              <Checkbox
                checked={override}
                onCheckedChange={(v) => setOverride(!!v)}
              />
              {t('mes.wip.override')}
            </Label>
            {override && (
              <Textarea
                rows={2}
                aria-label={t('mes.wip.override')}
                value={ovReason}
                onChange={(e) => setOvReason(e.target.value)}
              />
            )}
          </div>
        )}
        <DialogFooter>
          <Button
            disabled={
              !to || !reason || (override && !ovReason.trim()) || m.isPending
            }
            onClick={() => m.mutate()}
          >
            {t('mes.wip.jump')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
