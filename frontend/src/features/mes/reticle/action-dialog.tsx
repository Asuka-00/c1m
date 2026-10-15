/** 光罩动作对话框（usage / hold / release / restore / 清洗 / 维修 / 检查 / scrap / life-reset / 上机 / 登记异常）。 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { toast } from 'sonner'
import { eqpApi } from '@/lib/api/mes/equipment'
import {
  BACKFILL_FIELD,
  bodySignature,
  reticleApi,
  type Reticle,
  type ReticleAction,
  type ReticleActionInput,
} from '@/lib/api/mes/reticle'
import { siteWallToIso } from '@/lib/site-tz'
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
import { useOperationKey } from '@/features/mes/common/idem-key'
import {
  ACTIONS,
  INCIDENT_KINDS,
  SLOT_MAX,
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
  // D80：一次操作一个 Idempotency-Key；内容不变的重试复用，改了字段或成功后换新 key
  const opKey = useOperationKey()
  const fields = ACTIONS[action].fields
  const m = useMutation({
    mutationFn: () => {
      // D82：补录时间不填不传；填了按站点时区转带偏移 ISO
      const { backfill_at, ...rest } = v
      const bf = BACKFILL_FIELD[action]
      const input: ReticleActionInput = {
        ...rest,
        ...(bf && backfill_at
          ? { [bf]: siteWallToIso(backfill_at) ?? undefined }
          : {}),
        defect_count:
          String(v.defect_count ?? '').trim() === ''
            ? undefined
            : Number(v.defect_count),
      }
      const key = opKey.key(bodySignature(action, input))
      return reticleApi.act(reticle.id, action, input, key)
    },
    onSuccess: () => {
      opKey.done()
      toast.success(t('mes.reticle.done', { action: actionLabel(action) }))
      qc.invalidateQueries({ queryKey: ['mes', 'reticle'] })
      onClose()
    },
    onError: (e) => toast.error(reticleErrorMessage(e, action)),
  })
  // 上机 / 登记异常：机台下拉取设备看板，取不到时退回手填机台 ID
  const needEqp = fields.includes('mount') || fields.includes('incident')
  const eqp = useQuery({
    queryKey: ['mes', 'eqp', 'board'],
    queryFn: eqpApi.board,
    enabled: needEqp,
    retry: false,
    staleTime: 60_000,
  })
  const set = (k: keyof ReticleActionInput) => (s: string) =>
    setV((o) => ({ ...o, [k]: s }))
  const submit = () => {
    const e = validateAction(action, v)
    setErrs(e)
    if (Object.keys(e).length === 0) m.mutate()
  }
  const line = (k: 'slot_code' | 'lot_id', max?: number) => (
    <div className='grid gap-1'>
      <Label htmlFor={`reticle-${k}`}>{t(`mes.reticle.field.${k}`)}</Label>
      <Input
        id={`reticle-${k}`}
        data-testid={`reticle-${k}`}
        maxLength={max}
        value={v[k] ?? ''}
        onChange={(e) => set(k)(e.target.value)}
      />
      <FieldErr msg={errs[k]} />
    </div>
  )
  const eqpField = (required: boolean) => (
    <div className='grid gap-1'>
      <Label htmlFor='reticle-equipment_id'>
        {t('mes.reticle.field.equipment_id')}
        {required ? ' *' : ''}
      </Label>
      {eqp.data?.length ? (
        <select
          id='reticle-equipment_id'
          data-testid='reticle-equipment_id'
          className='h-9 rounded-md border border-input bg-transparent px-2 text-sm'
          value={v.equipment_id ?? ''}
          onChange={(e) => set('equipment_id')(e.target.value)}
        >
          <option value=''>—</option>
          {eqp.data.map((x) => (
            <option key={x.id} value={x.id}>
              {x.code} {x.name}
            </option>
          ))}
        </select>
      ) : (
        <Input
          id='reticle-equipment_id'
          data-testid='reticle-equipment_id'
          value={v.equipment_id ?? ''}
          onChange={(e) => set('equipment_id')(e.target.value)}
        />
      )}
      <FieldErr msg={errs.equipment_id} />
    </div>
  )
  const text = (
    k: 'reason' | 'comment' | 'note' | 'description',
    required: boolean
  ) => (
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
        {fields.includes('mount') && (
          <>
            {eqpField(true)}
            {line('slot_code', SLOT_MAX)}
          </>
        )}
        {fields.includes('incident') && (
          <>
            {sel('kind', [...INCIDENT_KINDS], 'incidentKind', true)}
            {eqpField(false)}
            {line('lot_id')}
            {text('description', false)}
          </>
        )}
        {fields.includes('reason') && text('reason', true)}
        {BACKFILL_FIELD[action] && (
          <div className='grid gap-1'>
            <Label htmlFor='reticle-backfill_at'>
              {t('mes.reticle.field.backfill_at')}
            </Label>
            <Input
              id='reticle-backfill_at'
              data-testid='reticle-backfill_at'
              type='datetime-local'
              value={v.backfill_at ?? ''}
              onChange={(e) => set('backfill_at')(e.target.value)}
            />
            <p className='text-xs text-muted-foreground'>
              {t('mes.reticle.backfillHint')}
            </p>
            <FieldErr msg={errs.backfill_at} />
          </div>
        )}
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
