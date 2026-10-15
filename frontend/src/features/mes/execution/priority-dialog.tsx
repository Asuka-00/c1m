/** 批次优先级变更对话框（急件 / Hot Lot）。 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Flame } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import { execApi, type ExecContext } from '@/lib/api/mes/execution'
import { Button } from '@/components/ui/button'
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
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'
import { Pick } from './exec-parts'

/** 优先级变更：选择新优先级（急件标记火焰图标）、备注，可选强制放行。 */
export function PriorityDialog({
  cx,
  open,
  canOverride,
  onOpenChange,
}: {
  cx: ExecContext
  open: boolean
  canOverride: boolean
  onOpenChange: (o: boolean) => void
}) {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const { entity } = useMesEntity('lot_history')
  const [pr, setPr] = useState('')
  const [comment, setComment] = useState('')
  const [override, setOverride] = useState(false)
  const [ovReason, setOvReason] = useState('')
  const list = useQuery({
    queryKey: ['mes', 'lot_priority', tk, 'all'],
    queryFn: () => mesApi.list('lot_priority', { page_size: 100 }),
    enabled: open,
  })
  const rows = (list.data?.data ?? []).filter(
    (r) => r.id !== cx.lot.priority_id
  )
  const m = useMutation({
    mutationFn: () =>
      execApi.priority(String(cx.lot.id), {
        priority_id: pr,
        comment: comment || undefined,
        override: override || undefined,
        override_reason: override ? ovReason : undefined,
      }),
    onSuccess: () => {
      toast.success(t('mes.prio.done'))
      onOpenChange(false)
      setPr('')
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => toast.error(mesErrorMessage(e, entity)),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className='flex items-center gap-2'>
            <Flame className='size-4 text-red-600' />
            {t('mes.prio.title')} · {String(cx.lot.code)}
          </DialogTitle>
          <DialogDescription>{t('mes.prio.desc')}</DialogDescription>
        </DialogHeader>
        <Pick
          id='prio-new'
          label={t('mes.prio.new')}
          required
          none={false}
          value={pr}
          onChange={setPr}
          options={rows.map((r) => ({
            id: r.id,
            label: `${r.is_hot ? '🔥 ' : ''}${String(r.code)} · ${String(r.name)}`,
          }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='prio-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='prio-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        {canOverride && (
          <Label className='flex items-center gap-2'>
            <Checkbox
              checked={override}
              onCheckedChange={(v) => setOverride(!!v)}
            />
            {t('mes.wip.override')}
          </Label>
        )}
        {override && (
          <Textarea
            rows={2}
            aria-label={t('mes.wip.override')}
            value={ovReason}
            onChange={(e) => setOvReason(e.target.value)}
          />
        )}
        <DialogFooter>
          <Button
            disabled={!pr || (override && !ovReason.trim()) || m.isPending}
            onClick={() => m.mutate()}
          >
            {t('mes.prio.title')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
